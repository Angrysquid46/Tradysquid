from pathlib import Path

OLD = "9564ab1d86669b082386875e3e4e2702543bfb2e"
NEW = "254d67d0cf2a796fd9689693c7b061ce98ae2c63"
FILES = (
    Path("RUN-AUDITED-TRADYSQUID-INSTALL.ps1"),
    Path("clean_rebuild_auto_handoff.py"),
    Path("test_visible_manual_installer.py"),
    Path("test_simple_upgrade_flow.py"),
)

for path in FILES:
    text = path.read_text(encoding="utf-8")
    count = text.count(OLD)
    if count < 1:
        raise SystemExit(f"Expected old clean commit was not found in {path}")
    path.write_text(text.replace(OLD, NEW), encoding="utf-8")
    print(f"repinned {path}: {count} reference(s)")

for temporary in (
    Path("scripts/repin_visible_bounded_rollback.py"),
    Path(".github/workflows/repin-visible-bounded-rollback.yml"),
):
    temporary.unlink(missing_ok=True)
