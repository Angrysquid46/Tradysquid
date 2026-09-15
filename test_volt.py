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


def test_sensitive_bounce_cannot_buy_call_against_unconfirmed_downtrend():
    values=[510-index*.12 for index in range(55)]+[503.5,503.56,503.63,503.70]
    observed=[{"close":x,"high":x+.04,"low":x-.04,"volume":1000} for x in values]
    contract={"data_class":"VERIFIED_REAL","side":"call","bid":.95,"ask":1.,"delta":.5,"option_symbol":"x"}
    decision=Volt().decide(datetime.now(),1000,{"tier":"A"},{"tier":"A","contracts":[contract]},observed)
    assert decision.action=="NO_ACTION"
    assert "conflicts with verified direction" in decision.reason
