"""
Tests for eve_complexity_tracker.py

Run: python test_complexity_tracker.py
     pytest test_complexity_tracker.py -v
"""

import sys
from eve_complexity_tracker import (
    ComplexityTracker,
    CHECKPOINT_BUDGET_TOKENS,
    DEESCALATION_ROUNDS,
    ABSOLUTE_ERROR_FLOOR,
    DELTA_SPIKE_THRESHOLD,
    LOCAL_MODELS,
    ESCALATION_MODEL,
    _trim_to_budget,
    _estimate_tokens,
)

LOCAL_MODEL = next(iter(LOCAL_MODELS))   # pick any local model for tests


# ── helpers ───────────────────────────────────────────────────────────────────

def _tc(name: str, path: str = "") -> dict:
    """Fake Ollama ToolCall dict."""
    args = {"path": path} if path else {}
    return {"function": {"name": name, "arguments": args}}


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def _make_messages(n: int = 4) -> list:
    msgs = [_msg("system", "You are Eve.")]
    for i in range(n):
        msgs.append(_msg("user", f"message {i}"))
        msgs.append(_msg("assistant", f"response {i}"))
    return msgs


def _ok(result: str = "ok") -> str:
    return result


def _err(msg: str = "Error: file not found") -> str:
    return msg


def _run_round(tracker, tool_calls, results, messages):
    """Helper: record a round and return should_escalate()."""
    tracker.record_round(tool_calls, results, messages)
    return tracker.should_escalate()


# ── 1. No escalation before 2 rounds ──────────────────────────────────────────

def test_no_escalate_before_two_rounds():
    tracker = ComplexityTracker(LOCAL_MODEL, _make_messages())
    msgs = _make_messages()
    # Even with a high-score first round, need 2 rounds for delta
    tcs = [_tc("read_file", "a.py"), _tc("read_file", "b.py"), _tc("read_file", "c.py")]
    tracker.record_round(tcs, [_ok()] * 3, msgs)
    assert not tracker.should_escalate(), "Should not escalate after only 1 round (no delta yet)"
    print("PASS  no escalation before 2 rounds")


# ── 2. No escalation on flat complexity ───────────────────────────────────────

def test_no_escalate_on_flat_complexity():
    """Round 1 touches 3 files (normal burst). Round 2 does nothing new. No escalation."""
    tracker = ComplexityTracker(LOCAL_MODEL, _make_messages())
    msgs = _make_messages()

    # Round 1 — 3 files, looks heavy but it's just round-1 burst
    tracker.record_round(
        [_tc("read_file", "a.py"), _tc("read_file", "b.py"), _tc("read_file", "c.py")],
        [_ok()] * 3,
        msgs,
    )
    # Round 2 — only 1 small read, score drops
    tracker.record_round(
        [_tc("read_file", "a.py")],
        [_ok()],
        msgs,
    )
    assert not tracker.should_escalate(), "Flat/declining score should NOT escalate"
    print("PASS  no escalation on flat complexity")


# ── 3. Escalation on 2 consecutive rising rounds ──────────────────────────────

def test_escalate_on_sustained_rise():
    """Complexity score climbs across rounds 2 and 3 → escalate."""
    tracker = ComplexityTracker(LOCAL_MODEL, _make_messages())
    msgs = _make_messages()

    # Round 1 — baseline
    tracker.record_round([_tc("read_file", "a.py")], [_ok()], msgs)
    # Round 2 — score rises (more files + error)
    tracker.record_round(
        [_tc("read_file", "b.py"), _tc("write_file", "c.py")],
        [_ok(), _err()],
        msgs,
    )
    # Round 3 — score rises again (3 files + error → 9.0 > round-2's 7.0)
    fired = tracker.should_escalate()  # check after round 2 (only 2 rounds so far, no prior delta)
    tracker.record_round(
        [_tc("write_file", "d.py"), _tc("write_file", "e.py"), _tc("write_file", "f.py")],
        [_err(), _err(), _err()],
        msgs,
    )
    assert tracker.should_escalate(), "2 consecutive rising rounds should trigger escalation"
    print("PASS  escalation on 2 consecutive rising rounds")


# ── 4. Escalation on single spike ────────────────────────────────────────────

def test_escalate_on_spike():
    """A single round with a very high delta should escalate immediately."""
    tracker = ComplexityTracker(LOCAL_MODEL, _make_messages())
    msgs = _make_messages()

    # Round 1 — near-zero score
    tracker.record_round([_tc("read_file", "a.py")], [_ok()], msgs)

    # Round 2 — huge spike: 4 files + error + large output
    large_result = "x" * 10_000
    tracker.record_round(
        [_tc("write_file", f"{i}.py") for i in range(4)],
        [_err()] + [large_result] * 3,
        msgs + [_msg("assistant", "x" * 5_000)],  # big token delta
    )
    assert tracker.should_escalate(), "Large single-round spike should trigger escalation"
    print("PASS  escalation on single spike")


# ── 5. Absolute error-floor fallback ─────────────────────────────────────────

def test_absolute_error_floor():
    """After ABSOLUTE_ERROR_FLOOR error rounds, escalate regardless of delta."""
    tracker = ComplexityTracker(LOCAL_MODEL, _make_messages())
    msgs = _make_messages()

    for i in range(ABSOLUTE_ERROR_FLOOR):
        tracker.record_round(
            [_tc("bash", "")],
            [_err("Error: something broke")],
            msgs,
        )

    assert tracker.should_escalate(), f"After {ABSOLUTE_ERROR_FLOOR} error rounds, must escalate"
    print(f"PASS  absolute error floor ({ABSOLUTE_ERROR_FLOOR} error rounds)")


# ── 6. No escalation on cloud model ──────────────────────────────────────────

def test_no_escalate_if_already_cloud():
    """Cloud model should never trigger escalation."""
    tracker = ComplexityTracker(ESCALATION_MODEL, _make_messages())
    msgs = _make_messages()
    for _ in range(5):
        tracker.record_round(
            [_tc("write_file", "a.py"), _tc("write_file", "b.py")],
            [_err()] * 2,
            msgs,
        )
    assert not tracker.should_escalate(), "Cloud model should never self-escalate"
    print("PASS  no escalation if already on cloud model")


# ── 7. Checkpoint stays within budget ────────────────────────────────────────

def test_checkpoint_budget_hard_cap():
    """Checkpoint must stay ≤ CHECKPOINT_BUDGET_TOKENS regardless of rounds."""
    # Build a large message history (simulating round 25)
    big_msgs = [_msg("system", "You are Eve.")] + [
        _msg(role, "word " * 200)
        for role in ["user", "assistant"] * 30
    ]
    trimmed = _trim_to_budget(big_msgs, CHECKPOINT_BUDGET_TOKENS)
    actual_tokens = _estimate_tokens([m for m in trimmed if m.get("role") != "system"])
    sys_tokens = _estimate_tokens([m for m in trimmed if m.get("role") == "system"])
    total = actual_tokens + sys_tokens
    assert total <= CHECKPOINT_BUDGET_TOKENS + 10, (  # +10 for rounding
        f"Checkpoint {total} tokens exceeds budget {CHECKPOINT_BUDGET_TOKENS}"
    )
    print(f"PASS  checkpoint hard cap ({total} <= {CHECKPOINT_BUDGET_TOKENS} tokens)")


def test_checkpoint_grows_bounded_across_rounds():
    """After many rounds, tracker._checkpoint stays within budget."""
    tracker = ComplexityTracker(LOCAL_MODEL, _make_messages())
    msgs = _make_messages()

    for i in range(20):
        msgs.append(_msg("assistant", f"doing work round {i}: " + "detail " * 100))
        msgs.append(_msg("tool", "tool_result " * 50))
        tracker.record_round(
            [_tc("read_file", f"file_{i}.py")],
            [_ok("content " * 30)],
            msgs,
        )

    chk_tokens = _estimate_tokens(tracker._checkpoint)
    assert chk_tokens <= CHECKPOINT_BUDGET_TOKENS + 10, (
        f"After 20 rounds, checkpoint is {chk_tokens} tokens — exceeds budget"
    )
    print(f"PASS  checkpoint bounded after 20 rounds ({chk_tokens} tokens)")


# ── 8. build_clean_thread() is bounded ───────────────────────────────────────

def test_clean_thread_bounded():
    """Total tokens in build_clean_thread() output stays manageable."""
    tracker = ComplexityTracker(LOCAL_MODEL, _make_messages())
    msgs = _make_messages()

    # Simulate a complex session
    for i in range(10):
        msgs.append(_msg("assistant", "response " * 50))
        tracker.record_round(
            [_tc("write_file", f"file_{i}.py")],
            [_err() if i % 3 == 0 else _ok()],
            msgs,
        )

    thread = tracker.build_clean_thread("Refactor the auth module")
    total = _estimate_tokens(thread)
    # STEER ~300 tokens + checkpoint ≤ CHECKPOINT_BUDGET_TOKENS → generous ceiling
    ceiling = CHECKPOINT_BUDGET_TOKENS + 400
    assert total <= ceiling, (
        f"clean_thread is {total} tokens — exceeds ceiling {ceiling}"
    )
    print(f"PASS  clean_thread bounded ({total} tokens, ceiling {ceiling})")


# ── 9. De-escalation fires after trivial tail ────────────────────────────────

def test_deescalate_after_trivial_rounds():
    """should_deescalate() fires when last DEESCALATION_ROUNDS are all trivial."""
    tracker = ComplexityTracker(LOCAL_MODEL, _make_messages())
    msgs = _make_messages()

    # Force escalation first
    tracker._escalated = True

    for _ in range(DEESCALATION_ROUNDS):
        tracker.record_round(
            [_tc("read_file", "a.py")],
            [_ok("some content")],
            msgs,
        )

    assert tracker.should_deescalate(), "Should de-escalate after trivial tail"
    print(f"PASS  de-escalation fires after {DEESCALATION_ROUNDS} trivial rounds")


# ── 10. De-escalation blocked by error ───────────────────────────────────────

def test_no_deescalate_on_error():
    tracker = ComplexityTracker(LOCAL_MODEL, _make_messages())
    msgs = _make_messages()
    tracker._escalated = True

    # 2 trivial rounds, then 1 error round
    for _ in range(DEESCALATION_ROUNDS - 1):
        tracker.record_round([_tc("read_file", "a.py")], [_ok()], msgs)
    tracker.record_round([_tc("bash", "")], [_err("Error: permission denied")], msgs)

    assert not tracker.should_deescalate(), "Error in recent round should block de-escalation"
    print("PASS  de-escalation blocked by error round")


# ── 11. De-escalation blocked by write tool ──────────────────────────────────

def test_no_deescalate_on_write():
    tracker = ComplexityTracker(LOCAL_MODEL, _make_messages())
    msgs = _make_messages()
    tracker._escalated = True

    for _ in range(DEESCALATION_ROUNDS - 1):
        tracker.record_round([_tc("read_file", "a.py")], [_ok()], msgs)
    tracker.record_round([_tc("write_file", "a.py")], [_ok()], msgs)

    assert not tracker.should_deescalate(), "Write tool in recent round should block de-escalation"
    print("PASS  de-escalation blocked by write tool")


# ── 12. No de-escalation before escalation ───────────────────────────────────

def test_no_deescalate_before_escalation():
    tracker = ComplexityTracker(LOCAL_MODEL, _make_messages())
    msgs = _make_messages()
    for _ in range(DEESCALATION_ROUNDS + 2):
        tracker.record_round([_tc("read_file", "a.py")], [_ok()], msgs)
    assert not tracker.should_deescalate(), "should_deescalate() must not fire if never escalated"
    print("PASS  no de-escalation before escalation")


# ── 13. Escalation is one-shot ────────────────────────────────────────────────

def test_escalation_is_oneshot():
    """After escalation fires once, should_escalate() never fires again."""
    tracker = ComplexityTracker(LOCAL_MODEL, _make_messages())
    msgs = _make_messages()

    # Drive to escalation
    tracker._escalated = False
    for _ in range(ABSOLUTE_ERROR_FLOOR + 1):
        tracker.record_round([_tc("bash", "")], [_err()], msgs)

    assert tracker.should_escalate()       # fires once
    tracker._escalated = True              # simulate server setting this
    assert not tracker.should_escalate()   # never again
    print("PASS  escalation is one-shot")


# ── runner ────────────────────────────────────────────────────────────────────

TESTS = [
    test_no_escalate_before_two_rounds,
    test_no_escalate_on_flat_complexity,
    test_escalate_on_sustained_rise,
    test_escalate_on_spike,
    test_absolute_error_floor,
    test_no_escalate_if_already_cloud,
    test_checkpoint_budget_hard_cap,
    test_checkpoint_grows_bounded_across_rounds,
    test_clean_thread_bounded,
    test_deescalate_after_trivial_rounds,
    test_no_deescalate_on_error,
    test_no_deescalate_on_write,
    test_no_deescalate_before_escalation,
    test_escalation_is_oneshot,
]

if __name__ == "__main__":
    failed = []
    for t in TESTS:
        try:
            t()
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
            failed.append(t.__name__)
        except Exception as e:
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
            failed.append(t.__name__)

    print(f"\n{'-' * 50}")
    if failed:
        print(f"FAILED {len(failed)}/{len(TESTS)}: {', '.join(failed)}")
        sys.exit(1)
    else:
        print(f"ALL {len(TESTS)} TESTS PASSED")
