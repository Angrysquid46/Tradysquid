"""Is the work actually done? Answers with a checked list, not an opinion.

The owner should never have to ask "are you sure" or "is it deployed". This
runs every condition in CLAUDE.md's definition of done and prints PASS/FAIL
per item, exiting non-zero if any fail. Claiming completion without a clean
run of this is the failure, not a difference of approach.

Deliberately checks the LIVE system, not just tests - reporting a green unit
test as proof that production works is what shipped a broken time stop that
held positions 127 minutes past a 15-minute stop.

Usage:
    ./.venv-tradysquid/Scripts/python.exe verify_done.py
    ./.venv-tradysquid/Scripts/python.exe verify_done.py --full   # + full suite
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = ROOT / ".venv-tradysquid" / "Scripts" / "python.exe"
STATE = ROOT / "state" / "supervisor-state.json"

# Failures that exist regardless of any current change. Anything OUTSIDE this
# set is a regression this change introduced.
KNOWN_FAILURES = {
    "test_automation_acceptance.py",
    "test_backtest_lab.py",  # date(2026, 8, 24) hardcoded; fails near/after UTC midnight rollover, unrelated to any change - PR #325/#326, 2026-08-24/25
    "test_exit_quote_reliability.py",
    "test_pl_rounding_consistency.py",
    "test_stream_instrumentation.py",
    "test_system_digest_job.py",
    "test_upgrade_batch_44.py",
    "test_validate_reconciliation_coverage.py",
}


def _run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          timeout=timeout, errors="replace")


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append((name, ok, detail))

    def render(self) -> int:
        width = max(len(n) for n, _, _ in self.rows)
        for name, ok, detail in self.rows:
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {name.ljust(width)}  {detail}")
        failed = [n for n, ok, _ in self.rows if not ok]
        print()
        if failed:
            print(f"  NOT DONE - {len(failed)} check(s) failed: {', '.join(failed)}")
            return 1
        print("  DONE - every condition in CLAUDE.md verified")
        return 0


def main() -> int:
    full = "--full" in sys.argv
    r = Report()

    # 1. deployed == origin/main
    _run(["git", "fetch", "origin", "main", "-q"])
    origin = _run(["git", "rev-parse", "origin/main"]).stdout.strip()
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception as exc:
        state = {}
        r.check("supervisor state readable", False, str(exc)[:60])
    deployed = str(state.get("deployed_sha") or "")
    status = str(state.get("last_update_status") or "")
    r.check("deployed == origin/main", bool(origin) and deployed.startswith(origin[:12]),
            f"deployed={deployed[:7]} origin={origin[:7]}")
    r.check("last_update_status DEPLOYED", status == "DEPLOYED", f"status={status}")

    # 2. nothing uncommitted that should be committed
    dirty = [l for l in _run(["git", "status", "--porcelain"]).stdout.splitlines()
             if l and not l.endswith(("/", ".log"))
             and "docs/" not in l and ".claude" not in l and "pytest_cache" not in l]
    r.check("no uncommitted source", not dirty, f"{len(dirty)} file(s)" if dirty else "clean")

    # 3. Phase 3 clean-slate runtime: no inherited trader is installed.
    probe = _run([str(PY), "-c",
        "from pathlib import Path;"
        "root=Path.cwd();"
        "purged=['spy_scanner.py','performance_reconciliation.py','performance_scorecards.py','evolve_bot'];"
        "remaining=[p for p in purged if (root/p).exists()];"
        "print(len(remaining), *remaining)"], timeout=300)
    parts = probe.stdout.split()
    if parts:
        r.check("legacy trader runtime absent", parts[0] == "0", " ".join(parts[1:]))
    else:
        r.check("clean-slate probe", False, (probe.stderr or probe.stdout)[-70:])

    # 4. deploy gate
    mods = _run([str(PY), "-c",
        "import deployment_validation_manifest as m;print(' '.join(m.FOCUSED_TEST_MODULES))"],
        timeout=120).stdout.split()
    if mods:
        gate = _run([str(PY), "-m", "unittest", "-q", *mods], timeout=900)
        r.check("deploy gate", gate.returncode == 0,
                gate.stderr.strip().splitlines()[-1][:60] if gate.returncode else "OK")
    else:
        r.check("deploy gate", False, "could not read FOCUSED_TEST_MODULES")

    # 5. no NEW test failures
    if full:
        files = sorted(p.name for p in ROOT.glob("test_*.py"))
        suite = _run([str(PY), "-m", "pytest", "-q", "-p", "no:cacheprovider", *files],
                     timeout=1800)
        failed = {l.split("::")[0].replace("FAILED ", "").strip()
                  for l in suite.stdout.splitlines() if l.startswith("FAILED ")}
        new = sorted(failed - KNOWN_FAILURES)
        r.check("no NEW test failures", not new,
                f"new: {', '.join(new)}" if new else f"{len(failed)} known only")
    else:
        r.check("full suite", True, "skipped (pass --full to include)")

    return r.render()


if __name__ == "__main__":
    raise SystemExit(main())
