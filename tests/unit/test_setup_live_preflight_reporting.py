from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "scripts" / "setup.ps1"


def test_setup_reports_exact_live_preflight_failure_and_preserves_warning() -> None:
    text = SETUP.read_text(encoding="utf-8")
    assert "$LivePreflightPath = Join-Path $State 'live-preflight.json'" in text
    assert "Remove-Item -LiteralPath $LivePreflightPath" in text
    assert "Get-Content -LiteralPath $LivePreflightPath -Raw | ConvertFrom-Json" in text
    assert "Live preflight failed: category=$Category; check=$Check; error=$ErrorText" in text
    assert "LIVE PREFLIGHT WARNING: category={0}; check={1}; error={2}" in text
    assert "live_preflight_receipt = $LivePreflightPath" in text
    assert "live_preflight_status = $livePreflightStatus" in text
    assert "live_preflight_tradier_status = $livePreflightTradierStatus" in text
    assert "live_preflight_warnings = @($livePreflightWarnings)" in text
    assert "throw 'Live read-only verification failed.'" not in text
