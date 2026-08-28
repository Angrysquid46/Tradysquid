from datetime import date

import scoreboard
from bots.riptide import preflight


def test_riptide_preflight_accepts_clean_deployed_state(tmp_path, monkeypatch):
    monkeypatch.setattr(scoreboard, "DB_PATH", tmp_path / "scoreboard.db")
    monkeypatch.setattr(preflight, "_head", lambda: "abc123")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "supervisor-state.json").write_text('{"deployed_sha":"abc123","last_update_status":"UP_TO_DATE"}')
    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.setattr(preflight, "instance_port_free", lambda port=8893: True)
    monkeypatch.setattr(preflight.market_data, "get_quote", lambda *a, **k: {"symbol": "SPY"})
    monkeypatch.setattr(preflight.market_data, "get_expirations", lambda *a, **k: ["2026-08-28"])
    assert all(item.passed for item in preflight.run(session_date=date(2026, 8, 28)))
