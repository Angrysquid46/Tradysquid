import pytest

from tradysquid.discord.contracts import split_text, validate_payload
from tradysquid.discord.reconciliation import MessageReconciler


def test_size_validation_and_split() -> None:
    with pytest.raises(ValueError):
        validate_payload({"content": "x" * 2001})
    assert all(len(chunk) <= 100 for chunk in split_text("x" * 250, 100))


class API:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.messages = {}

    def create_message(self, channel_id, payload):
        if self.fail:
            raise RuntimeError("down")
        self.messages["1"] = {"id": "1", **payload}
        return {"id": "1"}

    def update_message(self, channel_id, message_id, payload):
        if self.fail:
            raise RuntimeError("down")
        self.messages[message_id] = {"id": message_id, **payload}
        return {"id": message_id}

    def get_message(self, channel_id, message_id):
        return self.messages.get(message_id)


class State:
    def __init__(self) -> None:
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def put(self, key, value):
        self.data[key] = value


def test_non_destructive_reconciliation() -> None:
    state = State()
    api = API()
    reconciler = MessageReconciler(api, state)

    first = reconciler.reconcile("x", "c", {"content": "one"}, "1")
    persisted_before_failure = dict(state.get("x"))
    api.fail = True

    with pytest.raises(RuntimeError):
        reconciler.reconcile("x", "c", {"content": "two"}, "2")

    assert first["action"] == "created"
    assert "action" not in persisted_before_failure
    assert state.get("x") == persisted_before_failure
