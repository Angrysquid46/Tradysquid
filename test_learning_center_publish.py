from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import learning_center_index as index
import learning_center_publish as pub


class FakeTracker:
    guild_id = "guild123"

    def __init__(self, channel_id: str = "chan1"):
        self.channel_id = channel_id
        self.posted: list[tuple[str, str, str]] = []

    def _request(self, method, path):
        return [{"id": self.channel_id, "name": index.chapter_channel_name(1)}]

    def upsert_singleton_message(self, channel_id, content, search_token):
        self.posted.append((channel_id, content, search_token))
        return f"msg-{len(self.posted)}", 0


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(index, "DB_PATH", Path(tempfile.mkdtemp()) / "lc.db")
    connection = index.connect_db()
    yield connection
    connection.close()


@pytest.fixture(autouse=True)
def _clear_channel_id_cache():
    """_resolve_channel_id() caches by channel name at module scope
    (intentional in production - channel IDs don't change within a
    process), so tests using different fake channel IDs for the same
    channel name must reset it between runs."""
    pub._CHANNEL_ID_CACHE.clear()
    yield
    pub._CHANNEL_ID_CACHE.clear()


def _sample_lesson() -> pub.Lesson:
    return pub.Lesson(
        lesson_number=1,
        title="Sample Lesson",
        topics=("t1",), keywords=("k1",), related_concepts=(),
        sections=(pub.Section("Overview", "Body one."), pub.Section("Example", "Body two.")),
    )


# --- dry run --------------------------------------------------------------

def test_dry_run_does_not_touch_discord_or_the_registry(db):
    tracker = FakeTracker()
    result = pub.publish_lesson(db, tracker, 1, _sample_lesson(), apply=False)
    assert result["applied"] is False
    assert result["cards"] == 2
    assert tracker.posted == []
    assert index.lessons_for_chapter(db, 1) == []


# --- apply ------------------------------------------------------------------

def test_apply_posts_one_card_per_section_and_registers_the_lesson(db):
    tracker = FakeTracker()
    result = pub.publish_lesson(db, tracker, 1, _sample_lesson(), apply=True)
    assert result["applied"] is True
    assert result["cards"] == 2
    assert len(tracker.posted) == 2

    registered = index.lessons_for_chapter(db, 1)
    assert len(registered) == 1
    assert registered[0]["lesson_id"] == "LC-01-01"
    assert registered[0]["publication_state"] == "PUBLISHED"
    assert registered[0]["jump_link"] == f"https://discord.com/channels/guild123/chan1/msg-1"


def test_apply_uses_the_first_posted_message_id_for_the_jump_link(db):
    tracker = FakeTracker(channel_id="chanXYZ")
    pub.publish_lesson(db, tracker, 1, _sample_lesson(), apply=True)
    registered = index.lessons_for_chapter(db, 1)[0]
    assert registered["jump_link"] == "https://discord.com/channels/guild123/chanXYZ/msg-1"
    assert registered["discord_message_id"] == "msg-1"


def test_search_token_includes_lesson_id_and_heading_so_reruns_update_not_duplicate(db):
    tracker = FakeTracker()
    pub.publish_lesson(db, tracker, 1, _sample_lesson(), apply=True)
    tokens = [entry[2] for entry in tracker.posted]
    assert tokens == ["LC-01-01:Overview", "LC-01-01:Example"]


def test_publish_chapter_covers_every_lesson_in_the_module(db, monkeypatch):
    class FakeModule:
        CHAPTER = 1
        LESSONS = [_sample_lesson(), pub.Lesson(
            lesson_number=2, title="Second", topics=(), keywords=(), related_concepts=(),
            sections=(pub.Section("Only", "Body."),),
        )]

    monkeypatch.setattr(pub, "load_chapter", lambda chapter: FakeModule)
    tracker = FakeTracker()
    results = pub.publish_chapter(db, tracker, 1, apply=True)
    assert [r["lesson_id"] for r in results] == ["LC-01-01", "LC-01-02"]
    assert len(index.lessons_for_chapter(db, 1)) == 2


# --- real chapter content sanity checks --------------------------------------

@pytest.mark.parametrize("chapter", [1, 2, 3, 4, 5])
def test_real_chapter_modules_load_and_every_lesson_has_sections(chapter):
    module = pub.load_chapter(chapter)
    assert module.CHAPTER == chapter
    assert module.LESSONS, f"chapter {chapter} has no lessons"
    for lesson in module.LESSONS:
        assert lesson.sections, f"{module.CHAPTER}/{lesson.lesson_number} has no sections"
        for section in lesson.sections:
            assert section.heading.strip()
            assert len(section.body.strip()) > 40, "section body looks like a placeholder"


def test_real_chapter_lesson_numbers_are_sequential_starting_at_one():
    for chapter in range(1, 6):
        module = pub.load_chapter(chapter)
        numbers = [lesson.lesson_number for lesson in module.LESSONS]
        assert numbers == list(range(1, len(numbers) + 1))
