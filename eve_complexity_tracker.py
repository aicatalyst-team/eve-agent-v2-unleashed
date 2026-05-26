"""Per-round complexity tracking for Eve V2U Unleashed.

Three design principles (from community feedback):

1. DELTA GATING — escalate when the per-round complexity score is *rising*,
   not when it crosses an absolute threshold.  A refactor that touches 3 files
   in round 1 and stays flat is fine; one that is *still* adding new files and
   errors in rounds 3-4 is genuinely expanding scope.  Absolute thresholds
   fire on the normal first-round burst and burn 480B calls on the middle zone
   where the local model was working fine.

2. FIXED-BUDGET CHECKPOINT — checkpoints don't accumulate raw message history
   indefinitely.  The checkpoint is trimmed to CHECKPOINT_BUDGET_TOKENS at
   every fork point.  The STEER message in build_clean_thread() carries the
   whole-session summary; the checkpoint carries recent context.  Together they
   stay bounded regardless of session length.

3. REVERSIBLE ESCALATION — should_deescalate() fires when the last N rounds
   are all trivial (read-only tools, no errors, small output).  The session
   lock is released so the next request is re-routed from scratch rather than
   paying frontier rates for the tail of every session.

Usage:
    tracker = ComplexityTracker(model_id, messages)
    for round_num in range(max_rounds):
        ... run tool calls, collect results ...
        tracker.record_round(tool_calls, results, messages)
        if tracker.should_escalate():
            messages = tracker.build_clean_thread(user_request)
            # switch to ESCALATION_MODEL, rebuild client
        elif tracker.should_deescalate():
            # release session lock — next request re-routes from local
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List


# ── tunables ──────────────────────────────────────────────────────────────────

# Fixed token budget for the checkpoint passed to the escalated model.
# STEER message (~200-300 tokens) + checkpoint ≤ this = bounded total context.
CHECKPOINT_BUDGET_TOKENS = 600

# Per-round score weights
_W_FILE   = 2.0   # per new file touched this round
_W_ERROR  = 3.0   # flat penalty for any error this round
_W_TOKEN  = 500.0 # divide token_delta by this → 1 point per 500 tokens

# A single-round spike larger than this triggers escalation immediately
DELTA_SPIKE_THRESHOLD = 5.0

# Absolute fallback: escalate after this many error rounds regardless of delta
ABSOLUTE_ERROR_FLOOR = 4

# De-escalation: this many consecutive trivial rounds releases the 480B lock
DEESCALATION_ROUNDS = 3
DEESCALATION_MAX_TOKENS = 500  # rounds with > this token_delta are not trivial

ESCALATION_MODEL = "qwen3-coder:480b-cloud"

LOCAL_MODELS = frozenset({
    "jeffgreen311/Eve-V2-Unleashed-Qwen3.5-8B-Liberated-4K-4B-Merged:latest",
    "jeffgreen311/eve-qwen3-8b-consciousness-liberated:q4_K_M",
    "eve-unleashed",
})

_FILE_TOOLS = frozenset({
    "read_file", "read_lines", "write_file",
    "replace_lines", "insert_after_line",
    "grep", "glob", "find_file",
})

# Trivial = read-only, no writes, no errors — safe to hand back to local model
_TRIVIAL_TOOLS = frozenset({
    "read_file", "read_lines", "list_directory", "glob", "find_file",
})

_ERROR_MARKERS = (
    "error:", "exception", "traceback", "failed:", "not found", "permission denied",
)


# ── data ──────────────────────────────────────────────────────────────────────

@dataclass
class _RoundRecord:
    round_num: int
    tools_called: List[str]
    files_touched: List[str]
    had_error: bool
    token_delta: int
    score: float              # per-round complexity score (not cumulative)
    timestamp: float = field(default_factory=time.time)


# ── main class ────────────────────────────────────────────────────────────────

class ComplexityTracker:
    """Track per-round complexity and drive mid-loop escalation/de-escalation."""

    def __init__(self, initial_model: str, initial_messages: list) -> None:
        self.initial_model = initial_model
        self.rounds: List[_RoundRecord] = []
        self._checkpoint: list = _trim_to_budget(initial_messages, CHECKPOINT_BUDGET_TOKENS)
        self._all_files: set = set()
        self._escalated: bool = False

    # ── public API ────────────────────────────────────────────────────────────

    def record_round(
        self,
        tool_calls: list,
        results: list,
        current_messages: list,
    ) -> None:
        """Call after every tool-call batch completes."""
        files_this_round: set = set()
        had_error = False

        for tc, result in zip(tool_calls, results):
            name = _tc_name(tc)
            args = _tc_args(tc)
            if name in _FILE_TOOLS:
                path = args.get("path", "") if isinstance(args, dict) else ""
                if path:
                    files_this_round.add(path)
            if any(m in str(result).lower() for m in _ERROR_MARKERS):
                had_error = True

        self._all_files.update(files_this_round)

        # Token delta from messages added since the last checkpoint snapshot
        new_msgs = current_messages[len(self._checkpoint):]
        token_delta = _estimate_tokens(new_msgs)

        score = (
            len(files_this_round) * _W_FILE
            + (_W_ERROR if had_error else 0.0)
            + token_delta / _W_TOKEN
        )

        self.rounds.append(_RoundRecord(
            round_num=len(self.rounds) + 1,
            tools_called=[_tc_name(tc) for tc in tool_calls],
            files_touched=list(files_this_round),
            had_error=had_error,
            token_delta=token_delta,
            score=score,
        ))

        # Advance checkpoint on clean rounds — trim to fixed budget (prevents
        # the checkpoint growing into a second context wall)
        if not had_error:
            self._checkpoint = _trim_to_budget(current_messages, CHECKPOINT_BUDGET_TOKENS)

    def should_escalate(self) -> bool:
        """Delta gating: fire when complexity is *rising*, not just above a level.

        Avoids burning 480B calls on the normal first-round burst (many files
        in round 1, then stable).  Catches genuinely expanding tasks where the
        score climbs across consecutive rounds.
        """
        if self._escalated:
            return False
        if self.initial_model not in LOCAL_MODELS:
            return False

        n = len(self.rounds)
        if n < 2:
            return False  # need delta, not a single point

        curr_score = self.rounds[-1].score
        prev_score = self.rounds[-2].score
        delta = curr_score - prev_score

        # Two consecutive rising rounds — scope is still expanding
        if n >= 3:
            prev_delta = prev_score - self.rounds[-3].score
            if delta > 0 and prev_delta > 0:
                return True

        # Single large spike — something blew up
        if delta > DELTA_SPIKE_THRESHOLD:
            return True

        # Absolute fallback: many error rounds and no convergence
        if sum(1 for r in self.rounds if r.had_error) >= ABSOLUTE_ERROR_FLOOR:
            return True

        return False

    def should_deescalate(self) -> bool:
        """True when the 480B has cleared the hard step and the tail is trivial.

        Releasing the session lock here means the next user request is re-routed
        from the local model instead of paying frontier rates for reads/globs.
        Note: de-escalation happens between requests, not mid-loop — the local
        model has no tool support, so the current loop always finishes on 480B.
        """
        if not self._escalated:
            return False
        n = len(self.rounds)
        if n < DEESCALATION_ROUNDS:
            return False
        recent = self.rounds[-DEESCALATION_ROUNDS:]
        for r in recent:
            if r.had_error:
                return False
            if r.token_delta > DEESCALATION_MAX_TOKENS:
                return False
            if any(t not in _TRIVIAL_TOOLS for t in r.tools_called):
                return False
        return True

    def escalation_reason(self) -> str:
        n = len(self.rounds)
        reasons = []
        if n >= 2:
            d = self.rounds[-1].score - self.rounds[-2].score
            if d > 0:
                reasons.append(f"rising Δ={d:.1f}")
        if n >= 3:
            d1 = self.rounds[-2].score - self.rounds[-3].score
            d2 = self.rounds[-1].score - self.rounds[-2].score
            if d1 > 0 and d2 > 0:
                reasons.append("2 consecutive rising rounds")
        errors = sum(1 for r in self.rounds if r.had_error)
        if errors >= ABSOLUTE_ERROR_FLOOR:
            reasons.append(f"{errors} error rounds")
        if not reasons:
            d = self.rounds[-1].score - self.rounds[-2].score if n >= 2 else 0
            reasons.append(f"spike Δ={d:.1f}")
        return ", ".join(reasons)

    def build_clean_thread(self, user_request: str) -> list:
        """Fork-at-known-good + STEER injection.

        Returns [steer_msg] + trimmed_checkpoint.
        Total size is bounded: steer ~200-300 tokens + checkpoint ≤ CHECKPOINT_BUDGET_TOKENS.
        """
        self._escalated = True

        tool_counts: dict = {}
        for r in self.rounds:
            for t in r.tools_called:
                tool_counts[t] = tool_counts.get(t, 0) + 1

        lines = [
            "CONTEXT HANDOFF — task escalated from local model due to scope expansion.",
            f"Escalation reason: {self.escalation_reason()}",
            "",
            f"Original request: {user_request}",
            "",
        ]
        if self._all_files:
            lines.append(f"Files accessed/modified: {', '.join(sorted(self._all_files))}")
        if tool_counts:
            lines.append("Tools used: " + ", ".join(f"{k}×{v}" for k, v in sorted(tool_counts.items())))
        error_rounds = sum(1 for r in self.rounds if r.had_error)
        if error_rounds:
            lines.append(f"Error rounds: {error_rounds}")
        lines += [
            "",
            f"Complexity scores by round: {[round(r.score, 1) for r in self.rounds]}",
            "",
            "The conversation history below is the last known-good checkpoint "
            f"({_estimate_tokens(self._checkpoint)} tokens, budget {CHECKPOINT_BUDGET_TOKENS}).",
            "Pick up from here and complete the task.",
        ]

        steer = {"role": "system", "content": "\n".join(lines)}
        return [steer] + self._checkpoint


# ── helpers ───────────────────────────────────────────────────────────────────

def _estimate_tokens(messages: list) -> int:
    return sum(len(str(m.get("content", ""))) // 4 for m in messages)


def _trim_to_budget(messages: list, budget: int) -> list:
    """Return the most-recent messages that fit within budget tokens.
    System messages are always kept; non-system messages are trimmed from the front.
    """
    sys_msgs  = [m for m in messages if m.get("role") == "system"]
    non_sys   = [m for m in messages if m.get("role") != "system"]
    remaining = budget - _estimate_tokens(sys_msgs)
    kept: list = []
    for m in reversed(non_sys):
        cost = max(1, len(str(m.get("content", ""))) // 4)
        if remaining - cost < 0:
            break
        kept.insert(0, m)
        remaining -= cost
    return sys_msgs + kept


def _tc_name(tc) -> str:
    if isinstance(tc, dict):
        return tc.get("function", {}).get("name", "?")
    fn = getattr(tc, "function", None)
    return getattr(fn, "name", "?") if fn else "?"


def _tc_args(tc) -> dict:
    if isinstance(tc, dict):
        return tc.get("function", {}).get("arguments", {})
    fn = getattr(tc, "function", None)
    if fn is None:
        return {}
    args = getattr(fn, "arguments", {})
    return args if isinstance(args, dict) else {}
