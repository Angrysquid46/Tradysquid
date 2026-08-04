from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLD = "eb1b04b2d6deeee42df8d939acb328e26d693f7f"
NEW = "f71acae7f7a502bdf64feda5b87e1f26111bffe6"
TARGETS = (
    ROOT / "RUN-AUDITED-TRADYSQUID-INSTALL.ps1",
    ROOT / "clean_rebuild_auto_handoff.py",
    ROOT / "test_simple_upgrade_flow.py",
    ROOT / "test_visible_manual_installer.py",
)


def main() -> None:
    changed = []
    for path in TARGETS:
        text = path.read_text(encoding="utf-8")
        count = text.count(OLD)
        if count != 1:
            raise SystemExit(f"Expected exactly one old clean commit in {path}, found {count}")
        path.write_text(text.replace(OLD, NEW), encoding="utf-8")
        changed.append(path)

    for path in TARGETS:
        text = path.read_text(encoding="utf-8")
        if OLD in text or text.count(NEW) != 1:
            raise SystemExit(f"Atomic repin verification failed for {path}")

    print("Repinned:")
    for path in changed:
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
