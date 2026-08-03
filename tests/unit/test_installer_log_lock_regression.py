from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts" / "install_clean_rebuild.ps1"
BODY = ROOT / "scripts" / "install_clean_rebuild_body.ps1"
BASE_HELPERS = ROOT / "scripts" / "installer_helpers.ps1"
RUNTIME_FIXES = ROOT / "scripts" / "installer_runtime_fixes.ps1"


def test_production_installer_injects_runtime_fix_after_base_helpers() -> None:
    wrapper = WRAPPER.read_text(encoding="utf-8")
    assert "install_clean_rebuild_body.ps1" in wrapper
    assert "installer_runtime_fixes.ps1" in wrapper
    assert "$InjectedBlock = $BaseHelperLine" in wrapper
    assert "[regex]::Replace" in wrapper
    assert "Start-Process -FilePath 'powershell.exe'" in wrapper


def test_preserved_installer_body_keeps_original_install_contract() -> None:
    body = BODY.read_text(encoding="utf-8")
    assert ". (Join-Path $ScriptRoot 'installer_helpers.ps1')" in body
    assert "Read-CanonicalCredentialHandoff" in body
    assert "Invoke-SetupProcess" in body
    assert "Read-CurrentSetupReceipt" in body
    assert "Restore-PreviousInstallation" in body


def test_redirected_logs_are_never_rewritten_in_place_by_active_override() -> None:
    fixes = RUNTIME_FIXES.read_text(encoding="utf-8")
    assert "setup-child-stdout.raw.log" in fixes
    assert "setup-child-stderr.raw.log" in fixes
    assert "RedirectStandardOutput = $RawStdoutPath" in fixes
    assert "RedirectStandardError = $RawStderrPath" in fixes
    assert "$Process.Dispose()" in fixes
    assert "Write-SanitizedLogFile -SourcePath $RawStdoutPath -DestinationPath $StdoutPath" in fixes
    assert "Write-SanitizedLogFile -SourcePath $RawStderrPath -DestinationPath $StderrPath" in fixes
    assert "Read-SharedTextFile" in fixes
    assert "Remove-FileAfterRedirectRelease" in fixes


def test_old_locked_rewrite_is_present_only_in_overridden_base_function() -> None:
    base = BASE_HELPERS.read_text(encoding="utf-8")
    fixes = RUNTIME_FIXES.read_text(encoding="utf-8")
    assert "[IO.File]::WriteAllText($StdoutPath" in base
    assert "function Invoke-SetupProcess" in fixes
    assert "Never rewrite the file used by RedirectStandardOutput" in fixes


def test_diagnostic_log_handling_cannot_replace_receipt_gate() -> None:
    body = BODY.read_text(encoding="utf-8")
    assert "if ($SetupExitCode -ne 0)" in body
    assert "if ($null -eq $SetupReceipt)" in body
    assert "if ($ReceiptStatus -ne 'PASS')" in body
