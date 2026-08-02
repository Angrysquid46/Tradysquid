"""Dependency-free repository secret and runtime-state hygiene check.

This is intentionally conservative and suitable for local pre-commit checks. It
never prints a discovered secret value; only the file, line, and detector name
are reported. Gitleaks can still be added on the worker later for history-wide
scanning, but this check provides immediate zero-install coverage.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAX_FILE_BYTES = 2_000_000
ALLOWED_EXAMPLES = {
    "sk-proj-your-complete-key",
    "your-email@example.com",
}
FORBIDDEN_TRACKED_PATHS = {
    ".env",
    ".env.worker",
    "state/ford-plays-log.csv",
    "state/discord-report-state.json",
}
PATTERNS = {
    "OpenAI key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    "GitHub token": re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    "Discord token": re.compile(
        r"\b[A-Za-z0-9_-]{23,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{20,}\b"
    ),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}
TEXT_SUFFIXES = {
    ".py",
    ".ps1",
    ".bat",
    ".cmd",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".md",
    ".txt",
    ".html",
    ".js",
    ".ts",
}


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    values = result.stdout.decode("utf-8", errors="replace").split("\0")
    return [ROOT / value for value in values if value]


def safe_excerpt(line: str) -> str:
    stripped = " ".join(line.strip().split())
    return (stripped[:90] + "…") if len(stripped) > 90 else stripped


def main() -> int:
    failures: list[str] = []
    for path in tracked_files():
        relative = path.relative_to(ROOT).as_posix()
        if relative in FORBIDDEN_TRACKED_PATHS:
            failures.append(f"{relative}: forbidden runtime or secret file is tracked")
            continue
        if path.suffix.casefold() not in TEXT_SUFFIXES:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for detector, pattern in PATTERNS.items():
                match = pattern.search(line)
                if not match:
                    continue
                if match.group(0) in ALLOWED_EXAMPLES:
                    continue
                failures.append(
                    f"{relative}:{line_number}: possible {detector}; "
                    f"context={safe_excerpt(line.replace(match.group(0), '[REDACTED]'))}"
                )
    if failures:
        print("Repository security hygiene failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Repository security hygiene passed; no tracked secret pattern was found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
