from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLD = "831559b1de1cd90eb8df47e32e5462eabf4b8fa0"
NEW = "eb1b04b2d6deeee42df8d939acb328e26d693f7f"
FILES = (
    ROOT / "RUN-AUDITED-TRADYSQUID-INSTALL.ps1",
    ROOT / "clean_rebuild_auto_handoff.py",
    ROOT / "test_visible_manual_installer.py",
    ROOT / "test_simple_upgrade_flow.py",
)
WORKFLOW = ROOT / ".github" / "workflows" / "repin-live-preflight-degraded-mode.yml"
SELF = Path(__file__).resolve()


def main() -> None:
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        count = text.count(OLD)
        if count < 1:
            raise RuntimeError(f"Expected old clean commit in {path.name}")
        updated = text.replace(OLD, NEW)
        if OLD in updated or NEW not in updated:
            raise RuntimeError(f"Repin validation failed for {path.name}")
        path.write_text(updated, encoding="utf-8")

    SELF.unlink()
    if WORKFLOW.exists():
        WORKFLOW.unlink()


if __name__ == "__main__":
    main()
