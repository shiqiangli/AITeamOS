"""Terminal command parsing and formatting helpers for Chat Kernel commands."""

from __future__ import annotations

import asyncio
import re
import shlex
from pathlib import Path

from .chat_kernel_catalog import (
    TERMINAL_ALLOWED_EXECUTABLES,
    TERMINAL_ALLOWED_GIT_COMMANDS,
    TERMINAL_ALLOWED_NPM_COMMANDS,
    TERMINAL_RUN_EN_RE,
)


def _clean_extracted_value(value: str) -> str:
    return value.strip().strip("\"'`“”‘’").strip()


def _extract_first(patterns: list[str], message: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            value = _clean_extracted_value(match.group(1))
            if value:
                return value
    return None


def strip_terminal_command_candidate(value: str) -> str:
    cleaned = _clean_extracted_value(value.strip())
    cleaned = re.split(r"[\n\r]", cleaned, maxsplit=1)[0].strip()
    cleaned = cleaned.strip("。；;")
    return cleaned[:240].strip()


def extract_terminal_command_line(message: str) -> str | None:
    code_match = re.search(r"`([^`\n]{1,240})`", message)
    if code_match:
        command = strip_terminal_command_candidate(code_match.group(1))
        if command:
            return command

    patterns = [
        r"\b(?:command|cmd)\s*[:=]\s*([^\n]{1,240})",
        r"\bterminal\.run\s*[:=]?\s*([^\n]{1,240})",
        r"(?:运行|执行|跑一下)\s*(?:terminal\s*)?(?:命令|command)?\s*[:：]?\s*([A-Za-z0-9_./:-][^\n]{0,239})",
        r"\b(?:run|execute)\s+(?:command\s*)?[:=]?\s*([A-Za-z0-9_./:-][^\n]{0,239})",
    ]
    for pattern in patterns:
        value = _extract_first([pattern], message)
        if value:
            command = strip_terminal_command_candidate(value)
            if command:
                return command

    stripped = message.strip()
    if re.match(r"^(?:pytest|npm\s+(?:test|run\s+build)|git\s+(?:status|diff|show)|pwd|ls)(?:\s|$)", stripped, re.IGNORECASE):
        return strip_terminal_command_candidate(stripped)
    return None


def is_terminal_run_request(message: str) -> bool:
    normalized = message.strip().lower()
    if "terminal.run" in normalized:
        return True
    if not TERMINAL_RUN_EN_RE.search(normalized):
        compact = re.sub(r"\s+", "", normalized)
        if not any(token in compact for token in ("执行命令", "运行命令", "跑命令", "终端执行", "terminal执行")):
            return False
    return extract_terminal_command_line(message) is not None


def terminal_argv_from_command(command_line: str) -> tuple[list[str] | None, str | None]:
    try:
        argv = shlex.split(command_line)
    except ValueError as exc:
        return None, f"Cannot parse terminal command: {exc}"
    if not argv:
        return None, "Terminal command is empty."
    executable = argv[0]
    if "/" in executable or executable not in TERMINAL_ALLOWED_EXECUTABLES:
        return None, f"Command executable is not allowed: {executable}"
    if executable == "npm" and tuple(argv[:2]) not in TERMINAL_ALLOWED_NPM_COMMANDS and tuple(argv[:3]) not in TERMINAL_ALLOWED_NPM_COMMANDS:
        return None, "Only `npm test` and `npm run build` are allowed."
    if executable == "git" and tuple(argv[:2]) not in TERMINAL_ALLOWED_GIT_COMMANDS:
        return None, "Only `git status`, `git diff`, and `git show` are allowed."
    if executable == "git" and any(arg == "-C" or arg.startswith("--git-dir") or arg.startswith("--work-tree") for arg in argv[2:]):
        return None, "Git workspace override arguments are not allowed."
    return argv, None


def terminal_cwd_from_raw(raw_cwd: str | None, workspace: Path) -> tuple[Path | None, str | None]:
    workspace = workspace.resolve()
    cwd = workspace if not raw_cwd else (workspace / raw_cwd).resolve()
    try:
        cwd.relative_to(workspace)
    except ValueError:
        return None, "cwd must stay inside the AITeamOS workspace."
    if not cwd.exists() or not cwd.is_dir():
        return None, f"cwd is not a directory: {raw_cwd}"
    return cwd, None


def validate_terminal_workspace_args(argv: list[str], cwd: Path, workspace: Path) -> str | None:
    workspace = workspace.resolve()
    for token in argv[1:]:
        if token.startswith("-"):
            continue
        path_token = token.split("::", maxsplit=1)[0]
        if "/" not in path_token and not path_token.startswith((".", "~")):
            continue
        if path_token.startswith("~"):
            return "Terminal path arguments must stay inside the AITeamOS workspace."
        candidate = Path(path_token)
        resolved = candidate.resolve() if candidate.is_absolute() else (cwd / candidate).resolve()
        try:
            resolved.relative_to(workspace)
        except ValueError:
            return "Terminal path arguments must stay inside the AITeamOS workspace."
    return None


async def run_terminal_command_collect(
    *,
    argv: list[str],
    cwd: Path,
    timeout_seconds: float = 120.0,
) -> tuple[int | None, str, bool]:
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        return process.returncode, stdout.decode("utf-8", errors="replace"), False
    except TimeoutError:
        process.kill()
        await process.wait()
        return None, "", True


def terminal_status(exit_code: int | None, timed_out: bool) -> str:
    return "timed out" if timed_out else ("completed" if exit_code == 0 else "failed")


def _relative_cwd(cwd: Path, workspace: Path) -> str:
    try:
        return str(cwd.relative_to(workspace.resolve()) or ".")
    except ValueError:
        return str(cwd)


def terminal_reply(
    *,
    command_line: str,
    cwd: Path,
    workspace: Path,
    exit_code: int | None,
    output: str,
    timed_out: bool,
) -> str:
    status = terminal_status(exit_code, timed_out)
    preview = output[-4000:].strip() or "(no output)"
    return (
        f"terminal.run {status}。\n\n"
        f"- Command: `{command_line}`\n"
        f"- CWD: `{_relative_cwd(cwd, workspace)}`\n"
        f"- Exit code: {exit_code if exit_code is not None else '-'}\n\n"
        "Output tail:\n"
        "```text\n"
        f"{preview}\n"
        "```"
    )


def terminal_evidence_ref(run_id: str) -> str:
    return f"terminal:{run_id}"


def terminal_report_content(
    *,
    command_line: str,
    cwd: Path,
    workspace: Path,
    exit_code: int | None,
    timed_out: bool,
    output: str,
) -> str:
    status = terminal_status(exit_code, timed_out)
    preview = output[-2000:].strip() or "(no output)"
    return (
        "Terminal command evidence.\n\n"
        f"Command: `{command_line}`\n"
        f"CWD: `{_relative_cwd(cwd, workspace)}`\n"
        f"Status: {status}\n"
        f"Exit code: {exit_code if exit_code is not None else '-'}\n\n"
        "Output tail:\n"
        "```text\n"
        f"{preview}\n"
        "```"
    )
