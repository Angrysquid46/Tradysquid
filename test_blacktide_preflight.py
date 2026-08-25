from datetime import date

import scoreboard
from bots.blacktide import preflight


def test_preflight_passes_clean_state_and_live_dependencies(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    monkeypatch.setattr(preflight, "_head", lambda: "abc123")
    (tmp_path / "state").mkdir()
    state = tmp_path / "state" / "supervisor-state.json"
    state.write_text('{"deployed_sha":"abc123","last_update_status":"DEPLOYED"}')
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.setattr(preflight, "instance_port_free", lambda port=8892: True)
    monkeypatch.setattr(preflight.market_data, "get_quote", lambda *a, **k: {"symbol": "SPY"})
    monkeypatch.setattr(preflight.market_data, "get_expirations", lambda *a, **k: ["2026-08-26"])
    checks = preflight.run(session_date=date(2026, 8, 26))
    assert checks and all(item.passed for item in checks)


def test_preflight_fails_closed_on_dirty_official_start(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    db = scoreboard.connect_db()
    scoreboard.record_trade_open(
        db, trade_id="existing", bot="BLACKTIDE", generation=1,
        opened_at="2026-08-26T09:00:00-05:00", side="CALL",
        contract_symbol="SPY_TEST", entry_price=1.0, contracts=1,
        entry_bankroll=1000.0,
    )
    db.close()
    monkeypatch.setattr(preflight, "_head", lambda: "abc123")
    (tmp_path / "state").mkdir()
    state = tmp_path / "state" / "supervisor-state.json"
    state.write_text('{"deployed_sha":"abc123","last_update_status":"DEPLOYED"}')
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.setattr(preflight, "instance_port_free", lambda port=8892: True)
    monkeypatch.setattr(preflight.market_data, "get_quote", lambda *a, **k: {"symbol": "SPY"})
    monkeypatch.setattr(preflight.market_data, "get_expirations", lambda *a, **k: ["2026-08-26"])
    checks = preflight.run(session_date=date(2026, 8, 26), require_clean_start=True)
    assert next(item for item in checks if item.name == "official-state").passed is False
