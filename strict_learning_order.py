"""Strictly order every channel inside the Discord Learning Center category.

Discord channel positions are guild-level values, and partial position updates can
leave unmentioned legacy or custom channels interleaved with numbered lessons.
This module reorders the complete category block, moves non-canonical channels
after the curriculum, then refetches Discord state and verifies the visible order.
"""

from __future__ import annotations

import re
import time
from typing import Any

import ford_scan
from learning_center_catalog import LEARNING_CHANNEL_ORDER

LEARNING_CATEGORY = "LEARNING CENTER"
MAX_ORDER_ATTEMPTS = 3


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")


def category_and_children(
    tracker: ford_scan.DiscordTracker,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    category = next(
        (
            item
            for item in channels
            if item.get("type") == 4
            and str(item.get("name") or "").casefold() == LEARNING_CATEGORY.casefold()
        ),
        None,
    )
    if not category:
        raise RuntimeError("Learning Center category was not found.")

    children = [
        item
        for item in channels
        if item.get("type") != 4
        and str(item.get("parent_id") or "") == str(category.get("id") or "")
    ]
    return category, children


def ordered_children(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return category children in the same deterministic order Discord displays."""
    return sorted(
        children,
        key=lambda item: (
            int(item.get("position") or 0),
            str(item.get("id") or ""),
        ),
    )


def desired_children(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Place the canonical curriculum first and every unrelated channel after it."""
    by_name: dict[str, dict[str, Any]] = {}
    for item in children:
        name = normalized(item.get("name") or "")
        if name and name not in by_name:
            by_name[name] = item

    missing = [name for name in LEARNING_CHANNEL_ORDER if name not in by_name]
    if missing:
        raise RuntimeError(
            "Cannot order missing Learning Center channels: " + ", ".join(missing)
        )

    canonical = [by_name[name] for name in LEARNING_CHANNEL_ORDER]
    canonical_ids = {str(item.get("id") or "") for item in canonical}
    extras = [
        item
        for item in ordered_children(children)
        if str(item.get("id") or "") not in canonical_ids
    ]
    return [*canonical, *extras]


def visible_ids(children: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("id") or "") for item in ordered_children(children)]


def enforce_learning_channel_order(
    tracker: ford_scan.DiscordTracker,
    *,
    attempts: int = MAX_ORDER_ATTEMPTS,
    retry_delay_seconds: float = 1.0,
) -> dict[str, Any]:
    """Apply, refetch, and verify the complete Learning Center channel order."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    last_actual: list[str] = []
    desired_names: list[str] = []
    for attempt in range(1, attempts + 1):
        category, children = category_and_children(tracker)
        desired = desired_children(children)
        desired_ids = [str(item.get("id") or "") for item in desired]
        desired_names = [normalized(item.get("name") or "") for item in desired]

        # Preserve the category's current guild-level block rather than assigning
        # positions from zero, which can collide with channels in other categories.
        base_position = min(
            (int(item.get("position") or 0) for item in children),
            default=0,
        )
        payload = [
            {
                "id": channel_id,
                "position": base_position + index,
                "parent_id": str(category.get("id") or ""),
                "lock_permissions": False,
            }
            for index, channel_id in enumerate(desired_ids)
        ]
        tracker._request(
            "PATCH",
            f"/guilds/{tracker.guild_id}/channels",
            payload,
        )

        _, refreshed = category_and_children(tracker)
        last_actual = visible_ids(refreshed)
        if last_actual == desired_ids:
            return {
                "ordered": len(desired_ids),
                "canonical": len(LEARNING_CHANNEL_ORDER),
                "extras": max(0, len(desired_ids) - len(LEARNING_CHANNEL_ORDER)),
                "attempts": attempt,
                "names": desired_names,
            }
        if attempt < attempts and retry_delay_seconds > 0:
            time.sleep(retry_delay_seconds)

    _, final_children = category_and_children(tracker)
    final_by_id = {
        str(item.get("id") or ""): normalized(item.get("name") or "")
        for item in final_children
    }
    actual_names = [final_by_id.get(channel_id, channel_id) for channel_id in last_actual]
    raise RuntimeError(
        "Discord did not preserve the required Learning Center order after "
        f"{attempts} attempts. Expected: {', '.join(desired_names)}. "
        f"Actual: {', '.join(actual_names)}."
    )
