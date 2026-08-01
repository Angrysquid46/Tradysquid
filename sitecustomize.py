"""Automatically apply Tradysquids Discord card styling to every Python service."""

from __future__ import annotations

import json

try:
    import requests
    from discord_cards import style_message_payload
except Exception:  # pragma: no cover - styling must never block service startup
    requests = None
    style_message_payload = None


def _is_discord_message_request(url: str, method: str, payload: object) -> bool:
    lowered = str(url or "").lower()
    if "discord.com/api/" not in lowered and "discordapp.com/api/" not in lowered:
        return False
    if method.upper() not in {"POST", "PATCH"}:
        return False
    if "/channels/" in lowered and "/messages" in lowered:
        return True
    return "/webhooks/" in lowered and isinstance(payload, dict) and "content" in payload


if requests is not None and style_message_payload is not None:
    _original_request = requests.sessions.Session.request

    def _styled_request(self, method: str, url: str, **kwargs):
        json_payload = kwargs.get("json")
        if _is_discord_message_request(url, method, json_payload):
            kwargs["json"] = style_message_payload(json_payload)
        else:
            data = kwargs.get("data")
            if (
                isinstance(data, dict)
                and "payload_json" in data
                and isinstance(data["payload_json"], str)
            ):
                try:
                    decoded = json.loads(data["payload_json"])
                except (TypeError, ValueError, json.JSONDecodeError):
                    decoded = None
                if _is_discord_message_request(url, method, decoded):
                    updated = dict(data)
                    updated["payload_json"] = json.dumps(
                        style_message_payload(decoded),
                        separators=(",", ":"),
                    )
                    kwargs["data"] = updated
        return _original_request(self, method, url, **kwargs)

    requests.sessions.Session.request = _styled_request
