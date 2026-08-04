from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "scripts" / "setup.ps1"
VERIFY_LIVE = ROOT / "scripts" / "verify_live.py"

SETUP_PATH_MARKER = "$LivePreflightPath = Join-Path $State 'live-preflight.json'\n"
SETUP_INSERT_AFTER = """    Invoke-SetupStage -Name 'canonical-credential-migration' -Action {
        Push-Location $Root
        try {
            & py -3.12 -m tradysquid.operations.credential_migration --root $Root
            if ($LASTEXITCODE -ne 0) {
                throw 'Credential migration failed.'
            }
        } finally {
            Pop-Location
        }
    }

"""
TOKEN_RECOVERY_STAGE = """    Invoke-SetupStage -Name 'discord-token-recovery' -Action {
        Remove-Item -LiteralPath $DiscordTokenRecoveryPath -Force -ErrorAction SilentlyContinue
        Push-Location $Root
        try {
            $SearchRoot = Split-Path -Parent $Root
            & py -3.12 -m tradysquid.operations.discord_token_recovery `
                --root $Root `
                --search-root $SearchRoot
            $RecoveryExitCode = $LASTEXITCODE

            if ($RecoveryExitCode -ne 0) {
                if (Test-Path -LiteralPath $DiscordTokenRecoveryPath -PathType Leaf) {
                    $RecoveryReceipt = Get-Content -LiteralPath $DiscordTokenRecoveryPath -Raw | ConvertFrom-Json
                    $RequiredAction = [string](Get-LiveReceiptProperty `
                        -InputObject $RecoveryReceipt `
                        -Name 'required_action' `
                        -DefaultValue 'RESET_DISCORD_BOT_TOKEN')
                    $RecoveryError = [string](Get-LiveReceiptProperty `
                        -InputObject $RecoveryReceipt `
                        -Name 'error' `
                        -DefaultValue 'No valid local Discord bot token was found.')
                    throw "Discord token recovery failed: action=$RequiredAction; error=$RecoveryError"
                }
                throw "Discord token recovery returned exit code $RecoveryExitCode without a receipt."
            }
        } finally {
            Pop-Location
        }
    }

"""
RESULT_MARKER = "        live_preflight_receipt = $LivePreflightPath\n"
VERIFY_IMPORT_MARKER = "from tradysquid.core.config import redact\n"
VERIFY_HEADER_MARKER = """    headers = {
        "Authorization": "Bot " + os.environ["DISCORD_BOT_TOKEN"],
        "User-Agent": "Tradysquid/0.1",
    }
"""
VERIFY_HEADER_REPLACEMENT = """    discord_token = normalize_discord_token(os.environ["DISCORD_BOT_TOKEN"])
    if not discord_token:
        raise LiveVerificationFailure(
            "CONFIGURATION",
            "discord-bot-token-normalization",
            "DISCORD_BOT_TOKEN is empty after safe normalization",
        )
    headers = {
        "Authorization": "Bot " + discord_token,
        "User-Agent": "Tradysquid/0.1",
    }
"""


def patch_setup() -> None:
    text = SETUP.read_text(encoding="utf-8")
    if "$DiscordTokenRecoveryPath" not in text:
        if SETUP_PATH_MARKER not in text:
            raise SystemExit("setup receipt path marker not found")
        text = text.replace(
            SETUP_PATH_MARKER,
            SETUP_PATH_MARKER
            + "$DiscordTokenRecoveryPath = Join-Path $State 'discord-token-recovery.json'\n",
            1,
        )

    if "Invoke-SetupStage -Name 'discord-token-recovery'" not in text:
        if SETUP_INSERT_AFTER not in text:
            raise SystemExit("canonical migration stage marker not found")
        text = text.replace(
            SETUP_INSERT_AFTER,
            SETUP_INSERT_AFTER + TOKEN_RECOVERY_STAGE,
            1,
        )

    if "discord_token_recovery_receipt = $DiscordTokenRecoveryPath" not in text:
        if RESULT_MARKER not in text:
            raise SystemExit("setup result marker not found")
        text = text.replace(
            RESULT_MARKER,
            "        discord_token_recovery_receipt = $DiscordTokenRecoveryPath\n"
            + RESULT_MARKER,
            1,
        )

    required = (
        "$DiscordTokenRecoveryPath = Join-Path $State 'discord-token-recovery.json'",
        "Invoke-SetupStage -Name 'discord-token-recovery'",
        "tradysquid.operations.discord_token_recovery",
        "action=$RequiredAction; error=$RecoveryError",
        "discord_token_recovery_receipt = $DiscordTokenRecoveryPath",
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise SystemExit("setup patch missing markers: " + ", ".join(missing))

    if text.index("Invoke-SetupStage -Name 'discord-token-recovery'") > text.index(
        "Invoke-SetupStage -Name 'dependency-installation'"
    ):
        raise SystemExit("Discord token recovery must run before dependency installation")

    SETUP.write_text(text, encoding="utf-8")


def patch_verify_live() -> None:
    text = VERIFY_LIVE.read_text(encoding="utf-8")
    import_line = (
        "from tradysquid.operations.discord_token_recovery import normalize_discord_token\n"
    )
    if import_line not in text:
        if VERIFY_IMPORT_MARKER not in text:
            raise SystemExit("verify_live import marker not found")
        text = text.replace(
            VERIFY_IMPORT_MARKER,
            VERIFY_IMPORT_MARKER + import_line,
            1,
        )

    if VERIFY_HEADER_MARKER in text:
        text = text.replace(VERIFY_HEADER_MARKER, VERIFY_HEADER_REPLACEMENT, 1)

    required = (
        import_line.strip(),
        'discord_token = normalize_discord_token(os.environ["DISCORD_BOT_TOKEN"])',
        '"discord-bot-token-normalization"',
        '"Authorization": "Bot " + discord_token',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise SystemExit("verify_live patch missing markers: " + ", ".join(missing))
    if '"Bot " + os.environ["DISCORD_BOT_TOKEN"]' in text:
        raise SystemExit("unsafe unnormalized Discord token header remains")

    VERIFY_LIVE.write_text(text, encoding="utf-8")


def main() -> None:
    patch_setup()
    patch_verify_live()


if __name__ == "__main__":
    main()
