from __future__ import annotations

import inspect

from tradysquid import app
from tradysquid.discord.bot import REQUIRED_COMMANDS
from tradysquid.discord.layout import CARD_ROUTES
from tradysquid.operations.scheduler import JOB_DEFINITIONS, LIVE_STARTUP_JOBS
from tradysquid.reporting.service import ReportingService
from tradysquid.scanner.service import ScanService


def test_shadow_trading_is_not_an_active_tradysquid_feature() -> None:
    job_ids = {job_id for job_id, _, _ in JOB_DEFINITIONS}

    assert "shadow-candidates" not in CARD_ROUTES
    assert "shadow-results" not in REQUIRED_COMMANDS
    assert "shadow-candidate-monitoring" not in job_ids
    assert "shadow-candidate-monitoring" not in LIVE_STARTUP_JOBS
    assert not hasattr(ReportingService, "shadow_analysis")

    scanner_source = inspect.getsource(ScanService)
    application_source = inspect.getsource(app.Application)
    assert "shadow_candidates" not in scanner_source
    assert "ShadowTrackingService" not in application_source
    assert "shadow-candidate-monitoring" not in application_source
