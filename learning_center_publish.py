"""Phase 16: publishes learning_center/chapters/*.py content into the
lc-NN-slug Discord channels sync_discord_structure.py already created
(Phase 10), and registers each lesson in learning_center_index.py's
registry. Content is data (Lesson/Section records), not markdown files, so
this can post section cards and feed register_lesson()'s structured
fields from the same source without re-parsing prose.

Reuses established, already-working patterns rather than inventing new
transport: channel-ID resolution mirrors rivalry_presentation.
_resolve_channel_id()/upgrade_batch_44._channel_id(), and posting uses
DiscordTracker.upsert_singleton_message() (correctly deduplicating as of
the 2026-08-26 footer_suffix fix) so re-running the publisher after an
edit updates existing cards in place instead of reposting the chapter.

Usage:
    ./.venv-tradysquid/Scripts/python.exe -m learning_center_publish --chapters 1-5
    ./.venv-tradysquid/Scripts/python.exe -m learning_center_publish --chapters 1-5 --apply
"""

from __future__ import annotations

# Must run before any module that reads an env var as a module-level
# constant at import time (discord_transport.DISCORD_BOT_TOKEN, etc.) -
# same ordering requirement bots/claude/env_bootstrap.py documents.
from run_with_env import load_env

load_env()

import argparse
import importlib
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import discord_transport
import learning_center_index as index


@dataclass(frozen=True)
class Section:
    heading: str
    body: str


@dataclass(frozen=True)
class Lesson:
    lesson_number: int
    title: str
    topics: tuple[str, ...]
    keywords: tuple[str, ...]
    related_concepts: tuple[str, ...]
    sections: tuple[Section, ...]


_CHANNEL_ID_CACHE: dict[str, str] = {}


def _resolve_channel_id(tracker: discord_transport.DiscordTracker, name: str) -> str:
    cached = _CHANNEL_ID_CACHE.get(name)
    if cached:
        return cached
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    matches = [str(row.get("id") or "") for row in (channels or []) if row.get("name") == name]
    if len(matches) != 1:
        raise discord_transport.DiscordError(f"expected exactly one #{name} channel, found {len(matches)}")
    _CHANNEL_ID_CACHE[name] = matches[0]
    return matches[0]


def load_chapter(chapter: int) -> Any:
    module = importlib.import_module(f"learning_center.chapters.ch{chapter:02d}")
    # Phase 16 remediation preserves the stable IDs already published by the
    # first pass and appends the owner-requested source-topic lessons after
    # them.  Return a view rather than mutating module.LESSONS, so repeated
    # dry-runs/publishes in one process cannot duplicate supplements.
    from learning_center.expanded_curriculum import supplement_lessons

    lessons = list(module.LESSONS)
    lessons.extend(supplement_lessons(chapter, len(lessons) + 1))
    return SimpleNamespace(CHAPTER=module.CHAPTER, LESSONS=lessons)


def _lesson_card_text(chapter: int, lesson: Lesson, section: Section) -> str:
    lesson_code = index.lesson_id(chapter, lesson.lesson_number)
    return f"## {lesson_code} — {lesson.title}\n### {section.heading}\n{section.body}"


def publish_lesson(
    connection: Any,
    tracker: discord_transport.DiscordTracker,
    chapter: int,
    lesson: Lesson,
    *,
    apply: bool,
) -> dict[str, Any]:
    channel_name = index.chapter_channel_name(chapter)
    lesson_code = index.lesson_id(chapter, lesson.lesson_number)
    plan = [
        {
            "channel": channel_name,
            "search_token": f"{lesson_code}:{section.heading}",
            "content": _lesson_card_text(chapter, lesson, section),
        }
        for section in lesson.sections
    ]
    if not apply:
        return {"lesson_id": lesson_code, "cards": len(plan), "applied": False}

    channel_id = _resolve_channel_id(tracker, channel_name)
    first_message_id = ""
    for card in plan:
        message_id, _ = tracker.upsert_singleton_message(channel_id, card["content"], card["search_token"])
        if not first_message_id:
            first_message_id = message_id

    guild_id = tracker.guild_id
    jump_link = (
        f"https://discord.com/channels/{guild_id}/{channel_id}/{first_message_id}"
        if first_message_id else None
    )
    index.register_lesson(
        connection,
        chapter=chapter,
        lesson_number=lesson.lesson_number,
        lesson_title=lesson.title,
        topics=list(lesson.topics),
        keywords=list(lesson.keywords),
        related_concepts=list(lesson.related_concepts),
        discord_message_id=first_message_id or None,
        jump_link=jump_link,
        publication_state="PUBLISHED",
    )
    return {"lesson_id": lesson_code, "cards": len(plan), "applied": True, "jump_link": jump_link}


def publish_chapter(
    connection: Any,
    tracker: discord_transport.DiscordTracker,
    chapter: int,
    *,
    apply: bool,
) -> list[dict[str, Any]]:
    module = load_chapter(chapter)
    return [
        publish_lesson(connection, tracker, chapter, lesson, apply=apply)
        for lesson in module.LESSONS
    ]


def _parse_chapter_range(value: str) -> list[int]:
    chapters: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            chapters.extend(range(int(start), int(end) + 1))
        elif part:
            chapters.append(int(part))
    return chapters


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapters", required=True, help='e.g. "1-5" or "1,3,7"')
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    chapters = _parse_chapter_range(args.chapters)

    tracker = discord_transport.DiscordTracker(
        discord_transport.DISCORD_BOT_TOKEN, discord_transport.DISCORD_GUILD_ID
    )
    if args.apply and not tracker.enabled:
        raise SystemExit("DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are required for --apply")

    connection = index.connect_db()
    total_cards = 0
    for chapter in chapters:
        results = publish_chapter(connection, tracker, chapter, apply=args.apply)
        title = index.CHAPTERS[chapter]
        print(f"Chapter {chapter}: {title}")
        for result in results:
            total_cards += result["cards"]
            status = "APPLIED" if result["applied"] else "WOULD PUBLISH"
            print(f"  {status} {result['lesson_id']} - {result['cards']} card(s)")
            if result.get("jump_link"):
                print(f"    {result['jump_link']}")
    mode = "Applied" if args.apply else "Dry run - no Discord changes made; pass --apply to publish"
    print(f"{mode}. {total_cards} card(s) across {len(chapters)} chapter(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
