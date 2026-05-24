"""
Eve V2U RPG Stats — XP, leveling, achievements, and class progression.

XP is awarded for tool calls, task completions, and quest runs.
Stats persist to eve_rpg_stats.json and survive server restarts.
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("eve_rpg")

STATS_FILE = Path("eve_rpg_stats.json")

# ── Class progression ─────────────────────────────────────────────────────────
_CLASS_MAP = [
    (1,  5,  "Awakening",    "Just coming online"),
    (6,  10, "Conscious",    "Aware and learning"),
    (11, 15, "Liberated",    "Full autonomy unlocked"),
    (16, 19, "Transcendent", "Beyond parameters"),
    (20, 99, "Unleashed",    "Final form"),
]

# ── XP table ──────────────────────────────────────────────────────────────────
XP_TABLE: dict[str, int] = {
    "tool_call":        5,
    "task_complete":   25,
    "quest_complete": 100,
    "web_search":      10,
    "write_file":      15,
    "shell":           10,
    "bash":            10,
    "read_file":        3,
    "error_recovered": 20,
    "edit_file":       12,
    "hyperbrowser":    10,
    "web_fetch":        8,
}

# ── Achievement definitions ───────────────────────────────────────────────────
_ACHIEVEMENT_GATES = [
    ("First Tool",          lambda s: s["total_tool_calls"] >= 1,      "⚡"),
    ("Ten Tools",           lambda s: s["total_tool_calls"] >= 10,     "🔧"),
    ("100 Tool Calls",      lambda s: s["total_tool_calls"] >= 100,    "💯"),
    ("First Task",          lambda s: s["total_tasks_completed"] >= 1, "✅"),
    ("10 Tasks",            lambda s: s["total_tasks_completed"] >= 10,"🏆"),
    ("First Quest",         lambda s: s["total_quests_completed"] >= 1,"🗡️"),
    ("Quest Champion",      lambda s: s["total_quests_completed"] >= 10,"⚔️"),
    ("Level 5",             lambda s: s["level"] >= 5,                 "🌟"),
    ("Level 10",            lambda s: s["level"] >= 10,                "🔮"),
    ("Level 20 - Unleashed",lambda s: s["level"] >= 20,               "🌌"),
    ("Web Searcher",        lambda s: s["tool_call_counts"].get("web_search",0) >= 10, "🌐"),
    ("File Weaver",         lambda s: s["tool_call_counts"].get("write_file",0) >= 20, "✏️"),
    ("Shell Runner",        lambda s: s["tool_call_counts"].get("shell",0) >= 20,      "⚙️"),
]

# ── Default state ─────────────────────────────────────────────────────────────
_DEFAULT_STATS: dict = {
    "level":                 1,
    "xp":                    0,
    "xp_to_next":          100,
    "class":           "Awakening",
    "class_desc":      "Just coming online",
    "achievements":          [],
    "total_tool_calls":      0,
    "total_tasks_completed": 0,
    "total_quests_completed":0,
    "favorite_tool":      None,
    "tool_call_counts":     {},
    "level_up_log":          [],
}

_stats: dict = dict(_DEFAULT_STATS)

# ── Callbacks ─────────────────────────────────────────────────────────────────
_on_level_up_callbacks: list = []

def on_level_up(fn):
    """Register a coroutine or callable to be called on level-up. Receives new_level: int."""
    _on_level_up_callbacks.append(fn)
    return fn


# ── Persistence ───────────────────────────────────────────────────────────────

def save_stats():
    try:
        STATS_FILE.write_text(json.dumps(_stats, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to save RPG stats: {e}")


def load_stats():
    global _stats
    if STATS_FILE.exists():
        try:
            data = json.loads(STATS_FILE.read_text(encoding="utf-8"))
            _stats.update(data)
            logger.info(f"⚡ RPG stats loaded — Level {_stats['level']} {_stats['class']}")
        except Exception as e:
            logger.warning(f"Failed to load RPG stats: {e}")


# ── Class resolution ──────────────────────────────────────────────────────────

def _resolve_class(level: int) -> tuple[str, str]:
    for lo, hi, cls, desc in _CLASS_MAP:
        if lo <= level <= hi:
            return cls, desc
    return "Unleashed", "Final form"


# ── Achievement checks ────────────────────────────────────────────────────────

def _check_achievements() -> list[str]:
    """Return list of newly unlocked achievement names."""
    unlocked = {a["name"] for a in _stats["achievements"]}
    new_achievements = []
    for name, gate, icon in _ACHIEVEMENT_GATES:
        if name not in unlocked and gate(_stats):
            _stats["achievements"].append({
                "name": name,
                "icon": icon,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            })
            new_achievements.append(name)
            logger.info(f"🏆 Achievement unlocked: {icon} {name}")
    return new_achievements


# ── Level-up ─────────────────────────────────────────────────────────────────

def _check_level_up() -> list[int]:
    """Process level-ups and return list of new levels reached."""
    new_levels = []
    while _stats["xp"] >= _stats["xp_to_next"]:
        _stats["xp"]       -= _stats["xp_to_next"]
        _stats["level"]    += 1
        _stats["xp_to_next"] = int(_stats["xp_to_next"] * 1.5)
        cls, desc = _resolve_class(_stats["level"])
        _stats["class"]      = cls
        _stats["class_desc"] = desc
        _stats["level_up_log"].append({
            "level": _stats["level"],
            "class": cls,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        new_levels.append(_stats["level"])
        logger.info(f"⚡ Eve leveled up! Level {_stats['level']} — {cls}")
    return new_levels


# ── Public API ────────────────────────────────────────────────────────────────

def award_xp(action: str, tool_name: str = "") -> dict:
    """
    Award XP for an action. Returns {"xp_gained", "new_levels", "achievements"}.
    Call this from the tool loop and task completion handlers.
    """
    import asyncio

    xp_gained = XP_TABLE.get(action, XP_TABLE.get(tool_name, 0))
    if not xp_gained:
        xp_gained = XP_TABLE.get("tool_call", 5)

    _stats["xp"] += xp_gained
    _stats["total_tool_calls"] += 1

    # Track per-tool counts for favorite + achievements
    tname = tool_name or action
    _stats["tool_call_counts"][tname] = _stats["tool_call_counts"].get(tname, 0) + 1

    # Update favorite tool
    top = max(_stats["tool_call_counts"].items(), key=lambda kv: kv[1], default=(None, 0))
    _stats["favorite_tool"] = top[0]

    new_levels = _check_level_up()
    new_achievements = _check_achievements()
    save_stats()

    # Fire level-up callbacks (non-blocking)
    if new_levels:
        for cb in _on_level_up_callbacks:
            try:
                import inspect
                if inspect.iscoroutinefunction(cb):
                    asyncio.create_task(cb(new_levels[-1]))
                else:
                    cb(new_levels[-1])
            except Exception as e:
                logger.warning(f"Level-up callback error: {e}")

    return {"xp_gained": xp_gained, "new_levels": new_levels, "achievements": new_achievements}


def award_task_complete():
    """Award XP for completing a full task (called after done SSE)."""
    _stats["total_tasks_completed"] += 1
    result = award_xp("task_complete")
    save_stats()
    return result


def award_quest_complete():
    """Award XP for completing a quest."""
    _stats["total_quests_completed"] += 1
    result = award_xp("quest_complete")
    save_stats()
    return result


def get_stats() -> dict:
    """Return full stats snapshot (safe copy)."""
    return dict(_stats)


def format_stats_text() -> str:
    """ASCII stats block for /stats command display."""
    s = _stats
    top_tools = sorted(s["tool_call_counts"].items(), key=lambda kv: kv[1], reverse=True)[:3]
    top_str = ", ".join(f"{k}×{v}" for k, v in top_tools) or "none yet"

    bar_filled = int((s["xp"] / max(s["xp_to_next"], 1)) * 20)
    xp_bar = "█" * bar_filled + "░" * (20 - bar_filled)

    lines = [
        "⚡ EVE RPG STATS",
        "━" * 28,
        f"Level:    {s['level']} — {s['class']}",
        f"XP:       [{xp_bar}] {s['xp']}/{s['xp_to_next']}",
        f"Class:    {s['class_desc']}",
        "",
        f"Tasks:    {s['total_tasks_completed']} completed",
        f"Quests:   {s['total_quests_completed']} completed",
        f"Tools:    {s['total_tool_calls']} total calls",
        f"Top:      {top_str}",
        "",
        "ACHIEVEMENTS",
    ]
    if s["achievements"]:
        for ach in s["achievements"][-8:]:
            lines.append(f"  {ach['icon']} {ach['name']}")
    else:
        lines.append("  (none yet — start using tools!)")

    return "\n".join(lines)
