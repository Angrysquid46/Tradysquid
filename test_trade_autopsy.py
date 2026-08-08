import trade_autopsy


def _row(**overrides):
    row = {
        "trade_id": "F-20260807-001",
        "ticker": "F",
        "play_type": "REGULAR",
        "call_or_put": "call",
        "strike": "14",
        "expiration": "2026-08-14",
        "timestamp": "2026-08-07T09:00:00-05:00",
        "entry_price": "0.60",
        "setup_score": "65.0",
        "market_regime": "BULLISH / CONTROLLED",
        "setup_reason": "intraday move is bullish (+1.0%)",
        "thesis": "regular call on F: intraday move is bullish (+1.0%)",
        "bid_ask_width_at_entry": "0.05",
        "open_interest_at_entry": "1000",
        "option_volume_at_entry": "300",
        "delta_at_entry": "0.50",
        "theta_at_entry": "-0.02",
        "iv_at_entry": "0.30",
        "max_favorable_pct": "5.0",
        "max_adverse_pct": "-10.0",
        "current_pl_pct": "3.0",
        "outcome": "OPEN",
    }
    row.update(overrides)
    return row


def test_flags_a_trade_that_never_went_green():
    row = _row(max_favorable_pct="0.0")
    report = trade_autopsy.autopsy(row)
    assert "NEVER WENT GREEN" in report


def test_does_not_flag_a_trade_that_went_favorable_first():
    row = _row(max_favorable_pct="9.0")
    report = trade_autopsy.autopsy(row)
    assert "NEVER WENT GREEN" not in report


def test_flags_a_loss_that_blows_past_its_own_stop_floor():
    # entry spread ~8.3%, widened stop floor around -23.3%; a -77% loss
    # blows straight through it - the CLF-shaped anomaly.
    row = _row(
        outcome="LOSS",
        bid_ask_width_at_entry="0.05",
        entry_price="0.60",
        exit_price="0.15",
        pct_gain_loss="-77.0",
        closed_at="2026-08-07T09:21:00-05:00",
        last_signal="STOP OUT",
    )
    report = trade_autopsy.autopsy(row)
    assert "EXECUTION ANOMALY" in report


def test_does_not_flag_a_loss_that_matches_its_stop_floor():
    row = _row(
        outcome="LOSS",
        bid_ask_width_at_entry="0.05",
        entry_price="0.60",
        exit_price="0.45",
        pct_gain_loss="-25.0",
        closed_at="2026-08-07T09:21:00-05:00",
        last_signal="STOP OUT",
    )
    report = trade_autopsy.autopsy(row)
    assert "EXECUTION ANOMALY" not in report


def test_flags_a_trade_entered_below_the_current_liquidity_floor():
    row = _row(open_interest_at_entry="200", option_volume_at_entry="5")
    report = trade_autopsy.autopsy(row)
    assert "predates the current filter" in report


def test_summary_counts_wins_losses_and_anomalies():
    clean_win = _row(trade_id="A", outcome="WIN", pct_gain_loss="20.0", max_favorable_pct="25.0")
    anomaly_loss = _row(
        trade_id="B",
        outcome="LOSS",
        pct_gain_loss="-77.0",
        exit_price="0.15",
        max_favorable_pct="0.0",
    )
    summary = trade_autopsy.summarize([clean_win, anomaly_loss])
    assert "Closed: 2 (1W / 1L)" in summary
    assert "Execution anomalies" in summary
    assert "B" in summary
