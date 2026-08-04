from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup.ps1"
WORKFLOW = ROOT / ".github" / "workflows" / "apply-live-preflight-setup-fix.yml"
SELF = Path(__file__).resolve()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} block, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = SETUP.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "$StageStatePath = Join-Path $State 'setup-stage-state.json'\n",
        "$StageStatePath = Join-Path $State 'setup-stage-state.json'\n"
        "$LivePreflightPath = Join-Path $State 'live-preflight.json'\n",
        "live preflight path",
    )

    text = replace_once(
        text,
        "$packagePath = $null\n$stageRecords = @()\n",
        "$packagePath = $null\n"
        "$livePreflightStatus = 'NOT STARTED'\n"
        "$livePreflightTradierStatus = 'NOT CHECKED'\n"
        "$livePreflightWarnings = @()\n"
        "$stageRecords = @()\n",
        "live preflight state initialization",
    )

    old_stage = """    Invoke-SetupStage -Name 'live-read-only-verification' -Action {
        Push-Location $Root
        try {
            & $Python -m scripts.verify_live
            if ($LASTEXITCODE -ne 0) {
                throw 'Live read-only verification failed.'
            }
        } finally {
            Pop-Location
        }
    }
"""

    new_stage = """    Invoke-SetupStage -Name 'live-read-only-verification' -Action {
        Remove-Item -LiteralPath $LivePreflightPath -Force -ErrorAction SilentlyContinue
        Push-Location $Root
        try {
            & $Python -m scripts.verify_live
            $LiveExitCode = $LASTEXITCODE

            if (-not (Test-Path -LiteralPath $LivePreflightPath -PathType Leaf)) {
                throw "Live verifier returned exit code $LiveExitCode without creating $LivePreflightPath"
            }

            $LiveReceipt = Get-Content -LiteralPath $LivePreflightPath -Raw | ConvertFrom-Json
            $script:livePreflightStatus = [string]$LiveReceipt.status
            $script:livePreflightTradierStatus = if ($LiveReceipt.tradier_live_status) {
                [string]$LiveReceipt.tradier_live_status
            } else {
                'NOT REPORTED'
            }
            $script:livePreflightWarnings = @($LiveReceipt.warnings)

            Write-Host ("Live preflight status: " + $script:livePreflightStatus)
            Write-Host ("Tradier live status: " + $script:livePreflightTradierStatus)

            foreach ($Warning in $script:livePreflightWarnings) {
                Write-Host (
                    "LIVE PREFLIGHT WARNING: category={0}; check={1}; error={2}" -f
                    $Warning.category,
                    $Warning.check,
                    $Warning.error
                ) -ForegroundColor Yellow
            }

            if ($LiveExitCode -ne 0 -or $LiveReceipt.status -ne 'PASS') {
                $Category = if ($LiveReceipt.category) { [string]$LiveReceipt.category } else { 'UNKNOWN' }
                $Check = if ($LiveReceipt.failed_check) { [string]$LiveReceipt.failed_check } else { 'unknown-check' }
                $ErrorText = if ($LiveReceipt.error) { [string]$LiveReceipt.error } else { 'No sanitized error was reported.' }
                throw "Live preflight failed: category=$Category; check=$Check; error=$ErrorText"
            }
        } finally {
            Pop-Location
        }
    }
"""
    text = replace_once(text, old_stage, new_stage, "live verification stage")

    text = replace_once(
        text,
        "        package_import = $packageImport\n        startup_receipt = Join-Path $State 'startup.json'\n",
        "        package_import = $packageImport\n"
        "        live_preflight_receipt = $LivePreflightPath\n"
        "        live_preflight_status = $livePreflightStatus\n"
        "        live_preflight_tradier_status = $livePreflightTradierStatus\n"
        "        live_preflight_warnings = @($livePreflightWarnings)\n"
        "        startup_receipt = Join-Path $State 'startup.json'\n",
        "setup result live preflight fields",
    )

    forbidden = "throw 'Live read-only verification failed.'"
    if forbidden in text:
        raise RuntimeError("Generic live verification failure remains in setup.ps1")

    SETUP.write_text(text, encoding="utf-8")

    test_path = ROOT / "tests" / "unit" / "test_setup_live_preflight_reporting.py"
    test_path.write_text(
        '''from __future__ import annotations

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
    assert "live_preflight_tradier_status = $livePreflightTradierStatus" in text
    assert "live_preflight_warnings = @($livePreflightWarnings)" in text
    assert "throw 'Live read-only verification failed.'" not in text
''',
        encoding="utf-8",
    )

    SELF.unlink()
    if WORKFLOW.exists():
        WORKFLOW.unlink()


if __name__ == "__main__":
    main()
