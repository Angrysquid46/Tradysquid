from tradysquid.reporting.periods import group_period
ROWS=[{'closed_at':'2026-08-03T10:00:00+00:00','pnl_dollars':10},{'closed_at':'2026-08-03T11:00:00+00:00','pnl_dollars':-5},{'closed_at':'2026-09-01T10:00:00+00:00','pnl_dollars':3}]
def test_daily_weekly_monthly_groups():
    assert len(group_period(ROWS,'daily'))==2; assert len(group_period(ROWS,'monthly'))==2; assert sum(x['sample_size'] for x in group_period(ROWS,'weekly').values())==3
