from __future__ import annotations

from .contracts import signature, validate_payload


class MessageReconciler:
    """Stable-message reconciliation with safe cross-channel rebinding."""

    def __init__(self, api, state_repository):
        self.api = api
        self.state = state_repository

    def reconcile(
        self,
        stable_id: str,
        channel_id: str,
        payload: dict,
        version: str,
    ):
        validate_payload(payload)
        sig = signature(payload)
        current = self.state.get(stable_id)
        same_channel = bool(
            current and str(current.get("channel_id")) == str(channel_id)
        )

        if (
            current
            and same_channel
            and current.get("signature") == sig
            and current.get("acknowledged")
        ):
            return {**current, "action": "unchanged"}

        if current and current.get("message_id") and same_channel:
            result = self.api.update_message(
                channel_id,
                current["message_id"],
                payload,
            )
            action = "updated"
        else:
            result = self.api.create_message(channel_id, payload)
            action = "rebound" if current and current.get("message_id") else "created"

        if not result or not result.get("id"):
            raise RuntimeError("Discord did not acknowledge the message")
        verified = self.api.get_message(channel_id, result["id"])
        if not verified or str(verified.get("id")) != str(result["id"]):
            raise RuntimeError("Discord message verification failed")

        state = {
            "stable_id": stable_id,
            "channel_id": str(channel_id),
            "message_id": str(result["id"]),
            "version": version,
            "signature": sig,
            "acknowledged": True,
            "action": action,
        }
        self.state.put(stable_id, state)
        return state
