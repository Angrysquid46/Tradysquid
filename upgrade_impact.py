"""Pre-deployment change-impact report and high-risk test gate."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config" / "upgrade-impact.json").read_text(encoding="utf-8"))


def changed_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD^", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, check=False,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def impacted(files: list[str]) -> list[str]:
    output = []
    for component, patterns in CONFIG["components"].items():
        if any(any(pattern.casefold() in path.casefold() for pattern in patterns) for path in files):
            output.append(component)
    return output


def report(files: list[str]) -> dict:
    components = impacted(files)
    high_risk = sorted(set(components).intersection(CONFIG["high_risk_components"]))
    tests_changed = any(Path(path).name.startswith("test_") for path in files)
    return {
        "changed_files": files,
        "impacted_components": components,
        "high_risk_components": high_risk,
        "tests_changed": tests_changed,
        "status": "PASS" if not high_risk or tests_changed else "BLOCK",
        "required_declarations": CONFIG["required_declarations"],
        "warning": (
            "High-risk integration changed without an accompanying test change."
            if high_risk and not tests_changed else ""
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = report(changed_files())
    print(json.dumps(payload, indent=2))
    return 1 if args.check and payload["status"] == "BLOCK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
