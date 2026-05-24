"""
Eve V2U Quest System — Autonomous background task queue.

Drop a .md file into workspace/quests/ and Eve picks it up on the next
QUEST_INTERVAL_MINUTES tick, runs it through the agentic loop, then deletes the file.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("eve_quest")

QUEST_DIR   = Path(os.getenv("EVE_WORKSPACE", ".")) / "quests"
QUEST_INTERVAL = int(os.getenv("QUEST_INTERVAL_MINUTES", "60")) * 60


# ── Quest state ──────────────────────────────────────────────────────────────

class QuestRunnerState:
    def __init__(self):
        self.running     = False
        self.current     = None   # filename of quest being run
        self.last_run_ts = None   # epoch of last completion
        self.completed   = []     # list of completed quest names (last 20)
        self.failed      = []     # list of (name, error) pairs (last 10)

_state = QuestRunnerState()


def get_state() -> dict:
    return {
        "running":     _state.running,
        "current":     _state.current,
        "last_run_ts": _state.last_run_ts,
        "completed":   _state.completed[-20:],
        "failed":      _state.failed[-10:],
        "pending":     list_quests(),
    }


# ── File helpers ──────────────────────────────────────────────────────────────

def list_quests() -> list[str]:
    QUEST_DIR.mkdir(parents=True, exist_ok=True)
    return [f.name for f in sorted(QUEST_DIR.glob("*.md"))]


def add_quest(title: str, content: str) -> str:
    QUEST_DIR.mkdir(parents=True, exist_ok=True)
    safe = title.replace(" ", "_").replace("/", "-").strip(".")[:80]
    path = QUEST_DIR / f"{safe}.md"
    # Avoid collisions with a timestamp suffix
    if path.exists():
        path = QUEST_DIR / f"{safe}_{int(time.time())}.md"
    path.write_text(content, encoding="utf-8")
    logger.info(f"🗡️ Quest added: {path.name}")
    return path.name


def delete_quest(name: str) -> bool:
    path = QUEST_DIR / name
    if path.exists() and path.suffix == ".md":
        path.unlink()
        return True
    return False


# ── Runner ────────────────────────────────────────────────────────────────────

async def quest_runner(
    run_task: Callable[[str, str], None],
    on_complete: Optional[Callable[[str, str], None]] = None,
    on_fail:     Optional[Callable[[str, str], None]] = None,
):
    """
    Background coroutine — checks for quests every QUEST_INTERVAL seconds.

    Args:
        run_task:    async callable(session_id, message) → response str
        on_complete: optional async callback(quest_name, response)
        on_fail:     optional async callback(quest_name, error_msg)
    """
    logger.info(f"🗡️ Quest runner started — checking every {QUEST_INTERVAL}s, dir={QUEST_DIR}")
    QUEST_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        await asyncio.sleep(QUEST_INTERVAL)

        quests = sorted(QUEST_DIR.glob("*.md"))
        if not quests:
            continue

        quest_file = quests[0]
        quest_name = quest_file.name
        _state.current = quest_name
        _state.running  = True

        try:
            content = quest_file.read_text(encoding="utf-8")
            logger.info(f"🗡️ Running quest: {quest_name} ({len(content)} chars)")

            response = await run_task("quest_runner", content)

            quest_file.unlink()
            _state.completed.append(quest_name)
            _state.last_run_ts = time.time()
            logger.info(f"✅ Quest complete: {quest_name}")

            if on_complete:
                try:
                    await on_complete(quest_name, response or "")
                except Exception as cb_err:
                    logger.warning(f"Quest on_complete callback failed: {cb_err}")

        except Exception as err:
            error_msg = str(err)
            logger.error(f"❌ Quest failed: {quest_name} — {error_msg}")
            _state.failed.append((quest_name, error_msg))
            # Move failed quest to a .failed suffix so it doesn't re-run immediately
            try:
                quest_file.rename(quest_file.with_suffix(".failed"))
            except Exception:
                pass
            if on_fail:
                try:
                    await on_fail(quest_name, error_msg)
                except Exception:
                    pass

        finally:
            _state.current = None
            _state.running  = False
