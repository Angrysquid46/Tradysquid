"""Owner ask, sourced from a Reddit suggestion: track performance across
market conditions, not just per strategy. classify_market_condition()
computes one universal trend+volatility tag from SPY's own daily price
action (no extra API calls - reuses the daily history already fetched for
the market chart), applied to every trade regardless of which strategy
opened it. candidate_to_row/entry_alert_text/format_market_condition_breakdown
carry that tag through storage, the journal card, and a lookback report.
"""

from __future__ import annotations

import spy_scanner as s


def _day(date_str: str, open_, high, low, close) -> dict:
    return {"date": date_str, "open": open_, "high": high, "low": low, "close": close}


def _flat_history(n: int, range_size: float = 2.0, base: float = 500.0) -> list[dict]:
    return [_day(f"2026-07-{i+1:02d}", base, base + range_size, base, base) for i in range(n)]


def test_returns_unknown_with_insufficient_history():
    assert s.classify_market_condition([])["label"] == "UNKNOWN"
    assert s.classify_market_condition(_flat_history(5))["label"] == "UNKNOWN"


def test_big_one_way_move_is_trending_up():
    prior = _flat_history(s.MARKET_CONDITION_VOL_LOOKBACK_DAYS, range_size=2.0)
    today = _day("2026-08-11", 500.0, 512.0, 499.0, 511.0)  # net +11 of a 13 range
    result = s.classify_market_condition(prior + [today])
    assert result["trend"] == "TRENDING_UP"


def test_big_one_way_move_down_is_trending_down():
    prior = _flat_history(s.MARKET_CONDITION_VOL_LOOKBACK_DAYS, range_size=2.0)
    today = _day("2026-08-11", 500.0, 501.0, 488.0, 489.0)  # net -11 of a 13 range
    result = s.classify_market_condition(prior + [today])
    assert result["trend"] == "TRENDING_DOWN"


def test_round_trip_day_is_choppy():
    prior = _flat_history(s.MARKET_CONDITION_VOL_LOOKBACK_DAYS, range_size=2.0)
    today = _day("2026-08-11", 500.0, 510.0, 495.0, 500.5)  # small net move, wide range
    result = s.classify_market_condition(prior + [today])
    assert result["trend"] == "CHOPPY"


def test_wide_range_versus_baseline_is_high_volatility():
    prior = _flat_history(s.MARKET_CONDITION_VOL_LOOKBACK_DAYS, range_size=2.0)
    today = _day("2026-08-11", 500.0, 505.0, 496.0, 500.5)  # 9pt range vs 2pt baseline
    result = s.classify_market_condition(prior + [today])
    assert result["volatility"] == "HIGH"


def test_narrow_range_versus_baseline_is_low_volatility():
    prior = _flat_history(s.MARKET_CONDITION_VOL_LOOKBACK_DAYS, range_size=10.0)
    today = _day("2026-08-11", 500.0, 501.0, 500.0, 500.5)  # 1pt range vs 10pt baseline
    result = s.classify_market_condition(prior + [today])
    assert result["volatility"] == "LOW"


def test_label_combines_both_axes():
    prior = _flat_history(s.MARKET_CONDITION_VOL_LOOKBACK_DAYS, range_size=2.0)
    today = _day("2026-08-11", 500.0, 512.0, 499.0, 511.0)
    result = s.classify_market_condition(prior + [today])
    assert result["label"] == f"{result['trend']} / {result['volatility']} VOL"


def test_zero_range_day_is_unknown_not_a_crash():
    prior = _flat_history(s.MARKET_CONDITION_VOL_LOOKBACK_DAYS)
    today = _day("2026-08-11", 500.0, 500.0, 500.0, 500.0)
    assert s.classify_market_condition(prior + [today])["label"] == "UNKNOWN"


def test_candidate_to_row_carries_the_market_condition_through():
    candidate = {
        "play_type": "SPY_0DTE_1M",
        "call_or_put": "call",
        "strike": 600,
        "expiration": "2026-08-11",
        "cost_or_credit": "0.50",
        "entry_price": 0.50,
        "delta": 0.4,
        "theta": -0.02,
        "iv": 0.3,
        "pop": 50,
        "max_profit": 100,
        "max_risk": 50,
        "breakeven": 600.5,
        "open_interest": 1000,
        "bid_ask_width": 0.05,
    }
    row = s.candidate_to_row(candidate, [], s.now_ct(), market_condition="TRENDING_UP / HIGH VOL")
    assert row["market_condition_at_entry"] == "TRENDING_UP / HIGH VOL"


def test_candidate_to_row_defaults_to_empty_market_condition():
    candidate = {
        "play_type": "SPY_0DTE_1M",
        "call_or_put": "call",
        "strike": 600,
        "expiration": "2026-08-11",
        "cost_or_credit": "0.50",
        "entry_price": 0.50,
        "delta": 0.4,
        "theta": -0.02,
        "iv": 0.3,
        "pop": 50,
        "max_profit": 100,
        "max_risk": 50,
        "breakeven": 600.5,
        "open_interest": 1000,
        "bid_ask_width": 0.05,
    }
    row = s.candidate_to_row(candidate, [], s.now_ct())
    assert row["market_condition_at_entry"] == ""


def test_entry_alert_text_shows_the_market_condition_line():
    row = {field: "" for field in s.LOG_HEADER}
    row.update(
        {
            "trade_id": "SPY-COND-001",
            "ticker": "SPY",
            "play_type": "SPY_0DTE_1M",
            "call_or_put": "call",
            "strike": "600",
            "expiration": "2026-08-11",
            "entry_price": "0.50",
            "market_condition_at_entry": "TRENDING_UP / HIGH VOL",
        }
    )
    content = s.entry_alert_text(row)
    assert "Market condition:** TRENDING_UP / HIGH VOL" in content


def test_market_condition_breakdown_groups_and_ranks_by_net_pl():
    rows = []
    for i in range(2):
        row = {field: "" for field in s.LOG_HEADER}
        row.update({
            "trade_id": f"T{i}", "outcome": "WIN", "pct_gain_loss": "20",
            "realized_pl_dollars": "20", "closed_at": "2026-08-11T12:00:00-05:00",
            "market_condition_at_entry": "TRENDING_UP / HIGH VOL",
        })
        rows.append(row)
    loss_row = {field: "" for field in s.LOG_HEADER}
    loss_row.update({
        "trade_id": "T-loss", "outcome": "LOSS", "pct_gain_loss": "-30",
        "realized_pl_dollars": "-30", "closed_at": "2026-08-11T12:00:00-05:00",
        "market_condition_at_entry": "CHOPPY / LOW VOL",
    })
    rows.append(loss_row)
    result = s.format_market_condition_breakdown(rows)
    assert "TRENDING_UP / HIGH VOL" in result
    assert "CHOPPY / LOW VOL" in result
    # Better-performing condition (2W, +$40 net) ranked before the loss (-$30).
    assert result.index("TRENDING_UP") < result.index("CHOPPY")


def test_market_condition_breakdown_ignores_untagged_rows():
    row = {field: "" for field in s.LOG_HEADER}
    row.update({"trade_id": "T-old", "outcome": "WIN", "pct_gain_loss": "10",
                "realized_pl_dollars": "10", "closed_at": "2026-08-11T12:00:00-05:00"})
    result = s.format_market_condition_breakdown([row])
    assert "No completed trades with a recorded market condition yet." in result
