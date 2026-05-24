"""
Eve Bash Safety Module — Prevents stuck commands and validates PowerShell syntax.
Detects problematic patterns that cause Eve to hang or loop.
"""

import re
import logging
from typing import Tuple

logger = logging.getLogger("eve_bash_safety")


# Commands that will ALWAYS block because they're interactive or unsupported
ABSOLUTELY_BLOCKED = {
    r'\bpython\s+\S+\s*<\s*',  # python < stdin (not supported in PowerShell properly)
    r'<\s*<\(',  # bash process substitution <(cmd) — not in PowerShell
    r'\|\s*while\b',  # pipe to while loop
    r'\|\s*read\b',  # pipe to read (bash only)
    r'&&',  # AND operator (not in PowerShell 5.1)
    r'\|\|',  # OR operator (not in PowerShell 5.1)
    r'&\s*$',  # Background execution in bash syntax
    r'yes\s*\|',  # yes | command (infinite stream)
    r'watch\s+',  # watch command (continuous monitoring)
    r'tail\s+-f',  # tail -f (continuous follow)
}

# Commands that are suspicious and should be flagged for user
SUSPICIOUS = {
    r'\bpython\s+\S+\s*\|',  # pipe python output (might hang if interactive)
    r'input\(',  # Python input() — will hang
    r'raw_input\(',  # Python raw_input() — will hang
    r'while\s+True',  # infinite loop
    r'for\s+\(\(\s*;\s*;\s*\)',  # infinite bash loop
}


def validate_bash_command(command: str) -> Tuple[bool, str]:
    """
    Validate that a bash command is safe to execute.
    
    Returns:
        (is_safe, error_message_or_warning)
    """
    if not command or not isinstance(command, str):
        return False, "Command is empty or not a string"
    
    command = command.strip()
    
    # ── Check for absolutely blocked patterns ──────────────────
    for pattern in ABSOLUTELY_BLOCKED:
        if re.search(pattern, command, re.IGNORECASE):
            reason = _describe_blocked_pattern(pattern)
            return False, (
                f"❌ BLOCKED: {reason}\n"
                f"Command: {command[:100]}\n\n"
                f"This command uses features not supported in PowerShell 5.1 or will cause Eve to hang.\n"
                f"Use separate commands instead."
            )
    
    # ── Check for suspicious patterns ──────────────────────────
    for pattern in SUSPICIOUS:
        if re.search(pattern, command, re.IGNORECASE):
            reason = _describe_suspicious_pattern(pattern)
            logger.warning(f"⚠️  Suspicious command pattern: {reason}\n  Command: {command[:80]}")
            # Don't block, but warn
    
    return True, ""


def fix_bash_command_for_powershell(command: str) -> str:
    """
    Attempt to fix common bash commands to work in PowerShell.
    Returns the fixed command, or original if no obvious fix.
    """
    cmd = command.strip()
    
    # Fix: Convert && (bash AND) to ; (PowerShell sequential)
    if '&&' in cmd:
        cmd = cmd.replace('&&', ';')
        logger.info(f"🔧 Fixed && → ; for PowerShell")
    
    # Fix: Convert || (bash OR) to simple sequential
    if '||' in cmd:
        # This is complex — just warn
        logger.warning(f"⚠️  Cannot safely convert || (bash OR) to PowerShell. Run commands separately.")
        return command
    
    # Fix: Remove bash process substitution <(...)
    if re.search(r'<\s*<\(', cmd):
        logger.warning(f"⚠️  Bash process substitution <(...) not supported. Use files or pipe instead.")
        return command
    
    # Fix: Remove background & if at end (not needed in streaming)
    if cmd.endswith('&'):
        cmd = cmd[:-1].strip()
        logger.info(f"🔧 Removed trailing & (not needed)")
    
    # Fix: python script | python — split into separate commands
    if 'python' in cmd and '|' in cmd:
        parts = cmd.split('|')
        if len(parts) >= 2 and 'python' in parts[0] and 'python' in parts[1]:
            logger.warning(f"⚠️  Piping between Python interpreters detected. Run separately.")
            return command
    
    return cmd


def timeout_for_command(command: str) -> int:
    """
    Determine appropriate timeout for a command.
    
    Returns timeout in seconds.
    """
    cmd_lower = command.lower()
    
    # Long operations get more time
    if any(kw in cmd_lower for kw in ['install', 'download', 'build', 'compile', 'docker']):
        return 120  # 2 minutes
    
    # Web operations
    if any(kw in cmd_lower for kw in ['curl', 'wget', 'fetch', 'request']):
        return 30
    
    # File operations
    if any(kw in cmd_lower for kw in ['copy', 'move', 'delete', 'mkdir', 'dir', 'ls']):
        return 10
    
    # Default
    return 15


def _describe_blocked_pattern(pattern: str) -> str:
    """Provide a human-readable explanation of why a pattern is blocked."""
    explanations = {
        r'\bpython\s+\S+\s*<\s*': "Python stdin redirection (<) — Use piping instead",
        r'<\s*<\(': "Bash process substitution — Not in PowerShell",
        r'\|\s*while\b': "Pipe to while loop — Use PowerShell foreach instead",
        r'\|\s*read\b': "Pipe to read — Bash only, not in PowerShell",
        r'&&': "Bash AND (&&) — Use semicolon (;) instead",
        r'\|\|': "Bash OR (||) — Use PowerShell try/catch instead",
        r'&\s*$': "Background execution (&) — Not reliable in streaming context",
        r'yes\s*\|': "Infinite yes command — Will hang",
        r'watch\s+': "watch command — Continuous monitoring not allowed",
        r'tail\s+-f': "tail -f — Continuous follow will hang",
    }
    
    for pat, desc in explanations.items():
        if pat == pattern:
            return desc
    
    return "Unknown blocked pattern"


def _describe_suspicious_pattern(pattern: str) -> str:
    """Provide a human-readable explanation of why a pattern is suspicious."""
    explanations = {
        r'\bpython\s+\S+\s*\|': "Python output piped — May hang if script is interactive",
        r'input\(': "Python input() call — Will hang waiting for input",
        r'raw_input\(': "Python raw_input() call — Will hang waiting for input",
        r'while\s+True': "Infinite loop — Will never exit",
        r'for\s+\(\(\s*;\s*;\s*\)': "Bash infinite loop — Will never exit",
    }
    
    for pat, desc in explanations.items():
        if pat == pattern:
            return desc
    
    return "Unknown suspicious pattern"


# ── Commands that need special handling ────────────────────

def should_run_in_background(command: str) -> bool:
    """
    Determine if a command should be run asynchronously without waiting.
    These are rare — most should block and return results.
    """
    cmd_lower = command.lower()
    return any(kw in cmd_lower for kw in ['poller', 'daemon', 'server', 'watch'])


def normalize_windows_paths(command: str) -> str:
    """
    Ensure Windows paths use consistent separators.
    PowerShell accepts both / and \ but / is more portable.
    """
    # Only convert backslashes that aren't escaped
    import os
    if os.name == 'nt':
        # This is complex — better to just warn users
        pass
    return command


# ── Safe command templates for file watcher ────────────────

SAFE_PYTHON_SCRIPT_RUNNER = """
$scriptPath = "{script_path}"
$arguments = @()
if ("{input_data}") {{ 
    $arguments = "-InputObject"
    $input_data = "{input_data}"
}}
& python $scriptPath @arguments
"""

SAFE_FILE_WATCHER_TEST = """
# Create test directory
if (-not (Test-Path "test_dir")) {{ mkdir "test_dir" }}

# Start watcher in background
$watcherJob = Start-Job -ScriptBlock {{
    cd "{workspace}"
    python file_watcher.py test_dir
}}

# Wait 5 seconds
Start-Sleep -Seconds 5

# Create test file
"test data" | Out-File "test_dir\\test_file.txt"

# Wait 2 seconds
Start-Sleep -Seconds 2

# Delete test file
Remove-Item "test_dir\\test_file.txt"

# Wait 2 seconds
Start-Sleep -Seconds 2

# Stop watcher
Stop-Job -Job $watcherJob

# Show results
Get-Content watch_log.txt -Tail 20
"""
