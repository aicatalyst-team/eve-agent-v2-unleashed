"""
Eve V2U Tool Router — Intent classification for tool usage decisions.

Replaces the inline action_keywords list in agent.py with nuanced verb
detection. Key fix over naive \b word boundaries: uses (?<![a-z]) lookbehind
so contractions like "let's write" or "can't search" match correctly.
Also handles common stemmed forms (editing, creates, created).
"""

import re
from typing import Tuple


# Verb → intent category mapping.
# Longer / more specific verbs should be checked before shorter ones to avoid
# "run" matching inside "return", etc. — the lookbehind handles this but ordering
# also prevents surprises on naive substring checks.
_ACTION_VERBS: dict[str, str] = {
    # File operations
    "rewrite":    "file_op",
    "write":      "file_op",
    "create":     "file_op",
    "edit":       "file_op",
    "modify":     "file_op",
    "update":     "file_op",
    "delete":     "file_op",
    "remove":     "file_op",
    "read":       "file_op",
    "rename":     "file_op",
    "move":       "file_op",
    "copy":       "file_op",
    # Execution / shell
    "execute":    "execution",
    "perform":    "execution",
    "implement":  "execution",
    "refactor":   "execution",
    "optimize":   "execution",
    "improve":    "execution",
    "build":      "execution",
    "deploy":     "execution",
    "fix":        "execution",
    "repair":     "execution",
    "run":        "execution",
    "install":    "execution",
    # Web / search
    "browse":     "web",
    "fetch":      "web",
    "search":     "web",
    "scrape":     "web",
    "download":   "web",
    "lookup":     "web",
    "look up":    "web",
    "look at":    "web",
    # Analysis
    "analyze":    "analysis",
    "analyse":    "analysis",
    "debug":      "analysis",
    "test":       "analysis",
    "check":      "analysis",
    "verify":     "analysis",
    "inspect":    "analysis",
    "audit":      "analysis",
    "review":     "analysis",
    # Search / locate
    "find":       "search",
    "locate":     "search",
    "grep":       "search",
    "list":       "search",
    "show":       "search",
}

# Suffixes to catch stemmed forms: editing, creates, created, optimizer, etc.
_SUFFIX = r"(?:s|es|ing|ed|er|ion|tion)?"

# Patterns that are NEVER tool-needs regardless of other signals
_NO_TOOL_PATTERNS = [
    r"\b(?:explain|describe|tell\s+me\s+about|what\s+is|how\s+does|why\s+is)\b",
    r"\b(?:define|definition|meaning\s+of)\b",
    r"\b(?:difference\s+between|compare|pros\s+and\s+cons|advantages|benefits)\b",
    r"\b(?:example\s+of|instance\s+of|overview\s+of)\b",
    r"\b(?:summarize|summarise)\b",
]

# Contextual signals that enable tools even without an explicit verb
_TOOL_CONTEXT_PATTERNS = [
    r"\b(?:path|file|folder|directory)s?\s*:",   # "path: /foo"
    r"\b(?:data|csv|json|sql|database)\s*:",      # "data: ..."
    r"\.(?:py|js|ts|html|json|yaml|toml|md|sh)\b",  # file extensions
    r"\b(?:what\s+tools|what\s+can\s+you|are\s+you\s+able|capabilities)\b",
    r"\b(?:all\s+files?|every\s+file|multiple\s+files?|entire\s+codebase)\b",
    r"\b(?:architecture|codebase|repository|repo)\b",
    r"\bgithub\.com\b",
]


def _verb_present(verb: str, text: str) -> bool:
    """
    True if verb (or a stemmed form) appears as a standalone word.

    Uses (?<![a-z]) instead of \\b as lookbehind so apostrophes in
    contractions ("let's write", "can't search") don't break matching.
    The trailing boundary uses \\b to correctly reject mid-word hits.
    """
    # Multi-word verbs ("look up", "look at") need a plain search
    if " " in verb:
        return verb in text

    escaped = re.escape(verb)
    pattern = rf"(?<![a-z]){escaped}{_SUFFIX}\b"
    return bool(re.search(pattern, text))


def classify_intent(message: str) -> Tuple[bool, str]:
    """
    Classify user intent and decide whether to enable tool use.

    Returns:
        (should_use_tools, intent_category)

    Intent categories:
        file_op, execution, web, analysis, search   — enable tools
        explanation, casual, short_message           — no tools
        file_context, data_processing, code_context  — enable tools (contextual)
        introspection                               — enable tools
    """
    lower = message.lower().strip()

    # ── 1. Explicit action verbs ─────────────────────────────────────────────
    for verb, category in _ACTION_VERBS.items():
        if _verb_present(verb, lower):
            # Veto: if the only signal is a pure explanation question, skip tools
            has_explain_pattern = any(re.search(p, lower) for p in _NO_TOOL_PATTERNS)
            if has_explain_pattern:
                # Still needs tools if there's a secondary action verb present
                secondary = any(
                    _verb_present(v, lower)
                    for v in _ACTION_VERBS
                    if v != verb and _ACTION_VERBS[v] != "analysis"
                )
                if not secondary:
                    return False, "explanation"
            return True, category

    # ── 2. Contextual patterns ───────────────────────────────────────────────
    for pattern in _TOOL_CONTEXT_PATTERNS:
        if re.search(pattern, lower):
            return True, "context_signal"

    # ── 3. Pure explanation patterns (no action) ─────────────────────────────
    if any(re.search(p, lower) for p in _NO_TOOL_PATTERNS):
        return False, "explanation"

    # ── 4. Short conversational messages ────────────────────────────────────
    if len(message) < 35:
        return False, "short_message"

    # ── 5. Medium messages with no keywords ─────────────────────────────────
    if len(message) < 150:
        return False, "casual"

    # ── 6. Long messages — look for any embedded action verb ─────────────────
    for verb in _ACTION_VERBS:
        if _verb_present(verb, lower):
            return True, "implicit_action"

    return False, "long_explanation"


def should_stream(intent_category: str) -> bool:
    """True for intent categories that benefit from live streaming output."""
    return intent_category in {
        "execution", "file_op", "analysis", "web",
        "data_processing", "implicit_action", "context_signal",
    }
