from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "tradysquid" / "discord" / "structure.py"
source = path.read_text(encoding="utf-8")
old = '''        candidate_ids = {
            _object_id(item)
            for item in self.cleanup_candidates
            if _category_name(item).upper() in INVENTED_CATEGORIES
            and _name(item).casefold() in MIGRATION_CHANNEL_NAMES
        }
'''
new = '''        candidate_ids = {
            _object_id(item)
            for item in self.cleanup_candidates
            if (
                _category_name(item).upper() in INVENTED_CATEGORIES
                and _name(item).casefold() in MIGRATION_CHANNEL_NAMES
            )
            or _name(item).casefold() == "shadow-candidates"
        }
        candidate_ids.update(
            _object_id(channel)
            for channel in all_channels
            if _name(channel).casefold() == "shadow-candidates"
        )
'''
if source.count(old) != 1:
    raise RuntimeError("Expected audited cleanup candidate block was not found once")
path.write_text(source.replace(old, new, 1), encoding="utf-8", newline="\n")
