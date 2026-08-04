from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SETUP = ROOT / "scripts" / "setup.ps1"
VERIFY_LIVE = ROOT / "scripts" / "verify_live.py"


def test_setup_recovers_discord_token_before_expensive_installation() -> None:
    text = SETUP.read_text(encoding="utf-8")
    recovery = text.index("Invoke-SetupStage -Name 'discord-token-recovery'")
    dependency = text.index("Invoke-SetupStage -Name 'dependency-installation'")
    tests = text.index("Invoke-SetupStage -Name 'automated-test-suite'")
    live = text.index("Invoke-SetupStage -Name 'live-read-only-verification'")

    assert recovery < dependency < tests < live
    assert "tradysquid.operations.discord_token_recovery" in text
    assert "--search-root $SearchRoot" in text
    assert "action=$RequiredAction; error=$RecoveryError" in text
    assert "discord_token_recovery_receipt = $DiscordTokenRecoveryPath" in text


def test_live_verifier_normalizes_token_before_authorization_header() -> None:
    text = VERIFY_LIVE.read_text(encoding="utf-8")
    assert (
        "from tradysquid.operations.discord_token_recovery import "
        "normalize_discord_token"
    ) in text
    assert 'discord_token = normalize_discord_token(os.environ["DISCORD_BOT_TOKEN"])' in text
    assert '"Authorization": "Bot " + discord_token' in text
    assert '"Bot " + os.environ["DISCORD_BOT_TOKEN"]' not in text
