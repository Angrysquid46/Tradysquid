from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLD = "254d67d0cf2a796fd9689693c7b061ce98ae2c63"
NEW = "831559b1de1cd90eb8df47e32e5462eabf4b8fa0"
FILES = (
    "RUN-AUDITED-TRADYSQUID-INSTALL.ps1",
    "clean_rebuild_auto_handoff.py",
    "test_visible_manual_installer.py",
    "test_simple_upgrade_flow.py",
)


def main() -> int:
    for relative in FILES:
        path = ROOT / relative
        text = path.read_text(encoding="utf-8")
        count = text.count(OLD)
        if count != 1:
            raise RuntimeError(
                f"Expected exactly one stale clean commit reference in {relative}, got {count}"
            )
        updated = text.replace(OLD, NEW)
        if OLD in updated or NEW not in updated:
            raise RuntimeError(f"Repin verification failed for {relative}")
        path.write_text(updated, encoding="utf-8")
        print(f"repinned {relative}: {count} reference")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
