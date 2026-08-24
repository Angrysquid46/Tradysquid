from __future__ import annotations

import inspect
import tempfile
from pathlib import Path

import pytest

import learning_center_index as lc


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(lc, "DB_PATH", Path(tempfile.mkdtemp()) / "learning_center_index.db")
    connection = lc.connect_db()
    yield connection
    connection.close()


# --- curriculum correctness ----------------------------------------------------

def test_all_forty_three_chapters_present():
    assert len(lc.CHAPTERS) == 43
    assert set(lc.CHAPTERS) == set(range(1, 44))


def test_spot_check_chapter_titles_against_the_spec():
    assert lc.CHAPTERS[1] == "Definitions"
    assert lc.CHAPTERS[2] == "Covered Call Writing"
    assert lc.CHAPTERS[25] == "LEAPS / Long-Term Option Strategies"
    assert lc.CHAPTERS[43] == "The Best Strategy?"


def test_chapter_channel_names_are_unique_and_within_discord_limits():
    names = [lc.chapter_channel_name(n) for n in range(1, 44)]
    assert len(set(names)) == 43
    assert all(len(name) <= 100 for name in names)
    assert all(name.startswith("lc-") for name in names)


def test_chapter_channel_names_do_not_collide_with_existing_declared_channels():
    """sync_discord_structure.py already declares these 43 lc- channels
    (this phase added them there) - the real check is that none of them
    collide with anything ELSE already declared, not with themselves."""
    import sync_discord_structure as sds

    new_names = {lc.chapter_channel_name(n) for n in range(1, 44)}
    other_existing = {channel.name for channel in sds.CHANNELS if channel.name not in new_names}
    assert other_existing & new_names == set()
    # And each lc- name appears in CHANNELS exactly once, not duplicated.
    all_names = [channel.name for channel in sds.CHANNELS]
    for name in new_names:
        assert all_names.count(name) == 1


def test_chapter_channel_name_rejects_out_of_range_chapter():
    with pytest.raises(ValueError, match="Unknown chapter"):
        lc.chapter_channel_name(0)
    with pytest.raises(ValueError, match="Unknown chapter"):
        lc.chapter_channel_name(44)


def test_lesson_id_format():
    assert lc.lesson_id(2, 1) == "LC-02-01"
    assert lc.lesson_id(43, 12) == "LC-43-12"


def test_lesson_id_rejects_out_of_range_chapter_or_bad_lesson_number():
    with pytest.raises(ValueError, match="Unknown chapter"):
        lc.lesson_id(99, 1)
    with pytest.raises(ValueError, match="lesson_number"):
        lc.lesson_id(1, 0)


# --- registry --------------------------------------------------------------

def test_register_lesson_round_trips(db):
    the_id = lc.register_lesson(
        db, chapter=2, lesson_number=1, lesson_title="What a covered call is",
        topics=["covered calls", "income"], keywords=["premium", "assignment"],
    )
    assert the_id == "LC-02-01"
    lessons = lc.lessons_for_chapter(db, 2)
    assert len(lessons) == 1
    assert lessons[0]["lesson_title"] == "What a covered call is"
    assert lessons[0]["topics"] == ["covered calls", "income"]
    assert lessons[0]["discord_channel"] == "lc-02-covered-call-writing"
    assert lessons[0]["publication_state"] == "DRAFT"


def test_register_lesson_is_idempotent_upsert(db):
    lc.register_lesson(db, chapter=1, lesson_number=1, lesson_title="v1")
    lc.register_lesson(db, chapter=1, lesson_number=1, lesson_title="v2")
    lessons = lc.lessons_for_chapter(db, 1)
    assert len(lessons) == 1
    assert lessons[0]["lesson_title"] == "v2"


def test_register_lesson_rejects_bad_chapter(db):
    with pytest.raises(ValueError, match="Unknown chapter"):
        lc.register_lesson(db, chapter=99, lesson_number=1, lesson_title="x")


def test_register_lesson_rejects_bad_publication_state(db):
    with pytest.raises(ValueError, match="Unknown publication_state"):
        lc.register_lesson(db, chapter=1, lesson_number=1, lesson_title="x", publication_state="MAYBE")


def test_lessons_for_chapter_ordered_by_lesson_number(db):
    lc.register_lesson(db, chapter=1, lesson_number=2, lesson_title="second")
    lc.register_lesson(db, chapter=1, lesson_number=1, lesson_title="first")
    lessons = lc.lessons_for_chapter(db, 1)
    assert [item["lesson_title"] for item in lessons] == ["first", "second"]


def test_search_lessons_matches_title_topics_and_keywords(db):
    lc.register_lesson(
        db, chapter=15, lesson_number=1, lesson_title="Put basics",
        topics=["protective puts"], keywords=["strike", "expiration"],
    )
    assert len(lc.search_lessons(db, "put basics")) == 1
    assert len(lc.search_lessons(db, "protective")) == 1
    assert len(lc.search_lessons(db, "strike")) == 1
    assert len(lc.search_lessons(db, "nonexistent")) == 0


# --- architectural isolation -----------------------------------------------

def test_no_trading_relevant_module_imports_learning_center_index():
    import backtest_lab
    import market_data_collector
    import rivalry
    import scoreboard

    for module in (backtest_lab, market_data_collector, rivalry, scoreboard):
        source = inspect.getsource(module)
        assert "learning_center_index" not in source, (
            f"{module.__name__} must never reference learning_center_index"
        )
