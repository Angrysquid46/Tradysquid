from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "tradysquid" / "discord" / "structure.py"
source = path.read_text(encoding="utf-8")
old_candidates = '''        candidate_ids = {
            _object_id(item)
            for item in self.cleanup_candidates
            if _category_name(item).upper() in INVENTED_CATEGORIES
            and _name(item).casefold() in MIGRATION_CHANNEL_NAMES
        }
'''
new_candidates = '''        candidate_ids = {
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
if source.count(old_candidates) != 1:
    raise RuntimeError("Expected audited cleanup candidate block was not found once")
source = source.replace(old_candidates, new_candidates, 1)
if source.count(old_guard) != 1:
    raise RuntimeError("Expected audited cleanup safety guard was not found once")
source = source.replace(old_guard, new_guard, 1)
path.write_text(source, encoding="utf-8", newline="\n")
