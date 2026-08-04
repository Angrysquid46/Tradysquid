from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "tradysquid" / "discord" / "structure.py"
source = path.read_text(encoding="utf-8")
old_guard = '''            if _name(channel).casefold() not in MIGRATION_CHANNEL_NAMES and (
                _category_name(channel).upper() not in INVENTED_CATEGORIES
            ):
                continue
'''
new_guard = '''            channel_name = _name(channel).casefold()
            if (
                channel_name not in MIGRATION_CHANNEL_NAMES
                and channel_name != "shadow-candidates"
                and _category_name(channel).upper() not in INVENTED_CATEGORIES
            ):
                continue
'''
if old_guard in source:
    source = source.replace(old_guard, new_guard, 1)
elif new_guard not in source:
    raise RuntimeError("Expected audited cleanup safety guard was not found")
path.write_text(source, encoding="utf-8", newline="\n")
