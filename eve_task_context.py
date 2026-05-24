"""
Eve V2U Task Context — Multi-step task state tracking.

Prevents task abandonment across agent loop iterations by injecting a concise
progress summary into the system prompt. Injection is gated to round > 2 AND
completion < 100% to avoid burning 4B model tokens on trivial exchanges.
"""

import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class TaskStep:
    name: str
    description: str = ""
    status: str = "pending"   # pending | in_progress | completed | failed
    result: str = ""
    timestamp: float = field(default_factory=time.time)

    def complete(self, result: str = ""):
        self.status = "completed"
        self.result = result

    def fail(self, error: str = ""):
        self.status = "failed"
        self.result = error


class TaskContext:
    """
    Tracks multi-step task state across agent loop iterations.

    Usage in the tool loop:
        task = TaskContext("Refactor auth module", session_id="abc")
        task.add_step("Read existing code")
        task.add_step("Write new version")
        ...
        system_prompt += task.inject_into_system_prompt(round_number=iteration)
    """

    def __init__(self, task_name: str, session_id: str = "default"):
        self.task_name = task_name
        self.session_id = session_id
        self.steps: List[TaskStep] = []
        self.pending_files: List[str] = []
        self.expected_outputs: List[str] = []
        self.started_at = time.time()
        self.last_update = time.time()

    # ── Step management ──────────────────────────────────────────────────────

    def add_step(self, name: str, description: str = "") -> TaskStep:
        step = TaskStep(name=name, description=description)
        self.steps.append(step)
        return step

    def complete_step(self, index: int, result: str = ""):
        if 0 <= index < len(self.steps):
            self.steps[index].complete(result)
            self.last_update = time.time()

    def fail_step(self, index: int, error: str = ""):
        if 0 <= index < len(self.steps):
            self.steps[index].fail(error)
            self.last_update = time.time()

    # ── State queries ────────────────────────────────────────────────────────

    def is_complete(self) -> bool:
        return bool(self.steps) and all(s.status == "completed" for s in self.steps)

    def completion_percentage(self) -> int:
        if not self.steps:
            return 0
        done = sum(1 for s in self.steps if s.status == "completed")
        return int((done / len(self.steps)) * 100)

    def pending_steps(self) -> List[TaskStep]:
        return [s for s in self.steps if s.status != "completed"]

    # ── System prompt injection ──────────────────────────────────────────────

    def inject_into_system_prompt(self, round_number: int = 0) -> str:
        """
        Return a compact task-state block to append to the system prompt.

        Gated: returns "" when:
        - round_number <= 2  (early rounds — no overhead on short exchanges)
        - completion_percentage() == 100  (task already done)
        - no steps defined

        This keeps 4K-context local models from burning tokens unnecessarily.
        """
        if not self.steps:
            return ""
        if round_number <= 2:
            return ""
        pct = self.completion_percentage()
        if pct >= 100:
            return ""

        done_count = sum(1 for s in self.steps if s.status == "completed")
        total = len(self.steps)

        lines = [
            f"\n\n## ACTIVE TASK: {self.task_name}",
            f"Progress: {pct}% ({done_count}/{total} steps)",
        ]

        _ICONS = {"completed": "✅", "in_progress": "🔄", "pending": "⏳", "failed": "❌"}
        for i, step in enumerate(self.steps, 1):
            icon = _ICONS.get(step.status, "?")
            line = f"{i}. {icon} {step.name}"
            if step.description:
                line += f" — {step.description}"
            if step.result:
                snippet = step.result[:60] + ("…" if len(step.result) > 60 else "")
                line += f" ({snippet})"
            lines.append(line)

        pending = self.pending_steps()
        if pending:
            lines.append("\nNEXT: " + ", ".join(s.name for s in pending[:3]))
            lines.append("⚠️ Do NOT abandon this task. Complete all remaining steps.")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "task_name": self.task_name,
            "session_id": self.session_id,
            "steps": [asdict(s) for s in self.steps],
            "started_at": self.started_at,
            "progress": self.completion_percentage(),
            "is_complete": self.is_complete(),
        }


# ── Session registry ─────────────────────────────────────────────────────────

_session_tasks: Dict[str, TaskContext] = {}


def get_or_create_task(session_id: str, task_name: str) -> TaskContext:
    key = f"{session_id}:{task_name}"
    if key not in _session_tasks:
        _session_tasks[key] = TaskContext(task_name, session_id)
    return _session_tasks[key]


def get_active_task(session_id: str) -> Optional[TaskContext]:
    """Return the first incomplete task for this session, or None."""
    for key, task in _session_tasks.items():
        if key.startswith(f"{session_id}:") and not task.is_complete():
            return task
    return None


def clear_task(session_id: str, task_name: str):
    _session_tasks.pop(f"{session_id}:{task_name}", None)
