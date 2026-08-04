from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup.ps1"

DOT_SOURCE = ". (Join-Path $PSScriptRoot 'live_preflight_receipt.ps1')"
START_MARKER = "    Invoke-SetupStage -Name 'live-read-only-verification' -Action {"
END_MARKER = "    Invoke-SetupStage -Name 'startup-task-registration' -Action {"

REPLACEMENT = r'''    Invoke-SetupStage -Name 'live-read-only-verification' -Action {
        Remove-Item -LiteralPath $LivePreflightPath -Force -ErrorAction SilentlyContinue
        Push-Location $Root
        try {
            & $Python -m scripts.verify_live
            $LiveExitCode = $LASTEXITCODE

            if (-not (Test-Path -LiteralPath $LivePreflightPath -PathType Leaf)) {
                throw "Live verifier returned exit code $LiveExitCode without creating $LivePreflightPath"
            }

            $LiveReceipt = Get-Content -LiteralPath $LivePreflightPath -Raw | ConvertFrom-Json
            $LiveSummary = Convert-LivePreflightReceipt -Receipt $LiveReceipt

            $script:livePreflightStatus = [string]$LiveSummary.status
            $script:livePreflightTradierStatus = [string]$LiveSummary.tradier_live_status
            $script:livePreflightWarnings = @($LiveSummary.warnings)

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

            if ($LiveExitCode -ne 0 -or $LiveSummary.status -ne 'PASS') {
                throw (
                    "Live preflight failed: category={0}; check={1}; error={2}" -f
                    $LiveSummary.category,
                    $LiveSummary.failed_check,
                    $LiveSummary.error
                )
            }
        } finally {
            Pop-Location
        }
    }

'''


def main() -> None:
    text = SETUP.read_text(encoding="utf-8")

    if DOT_SOURCE not in text:
        strict = "Set-StrictMode -Version Latest\n"
        if strict not in text:
            raise SystemExit("StrictMode marker not found")
        text = text.replace(strict, strict + DOT_SOURCE + "\n", 1)

    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("Live preflight setup stage markers were not found")

    text = text[:start] + REPLACEMENT + text[end:]

    forbidden = (
        "$LiveReceipt.tradier_live_status",
        "$LiveReceipt.warnings",
        "$LiveReceipt.category",
        "$LiveReceipt.failed_check",
        "$LiveReceipt.error",
    )
    found = [value for value in forbidden if value in text]
    if found:
        raise SystemExit("Unsafe StrictMode receipt access remains: " + ", ".join(found))

    required = (
        DOT_SOURCE,
        "Convert-LivePreflightReceipt -Receipt $LiveReceipt",
        "$LiveSummary.tradier_live_status",
        "$LiveSummary.failed_check",
    )
    missing = [value for value in required if value not in text]
    if missing:
        raise SystemExit("Required repaired setup markers are missing: " + ", ".join(missing))

    SETUP.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
