from datetime import datetime

import scoreboard
from bots.volt.engine import Volt
from bots.volt.preflight import INSTANCE_PORT


def _bars(step=.12):
    return [{"close":100+i*step,"high":100+i*step+.05,"low":100+i*step-.05} for i in range(20)]


def test_volt_has_unique_port_and_selected_sensitive_signal():
    assert INSTANCE_PORT == 8896
    side, score, state = Volt.signal(_bars(.06))
    assert side == "call"
    assert state == "IMPULSE"
    assert score >= .60


def test_volt_is_registered_with_clean_referee_state(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    c=scoreboard.connect_db()
    try:
        assert "VOLT" in scoreboard.BOTS
        assert scoreboard.current_generation(c,"VOLT") == 1
        assert scoreboard.current_bankroll(c,"VOLT") == 1000
        assert scoreboard.current_position_status(c,"VOLT") is None
    finally:c.close()


def test_owner_reset_preserves_history_and_starts_new_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    c=scoreboard.connect_db()
    try:
        scoreboard.record_generation_event(c,bot="VOLT",generation=1,event="RESET",detail="owner reset")
        scoreboard.record_generation_event(c,bot="VOLT",generation=2,event="STARTED",detail="fresh comparison")
        assert scoreboard.current_generation(c,"VOLT") == 2
        assert scoreboard.current_bankroll(c,"VOLT") == 1000
    finally:c.close()
