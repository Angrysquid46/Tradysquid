# Tradysquids Remote Control

This removes the manual update-and-restart routine.

## One-time installation

After pulling this version onto the laptop:

1. Close the old Command Bot, Information Engine, and ngrok CMD windows.
2. Double-click `INSTALL-REMOTE-CONTROL.cmd`.
3. Leave the laptop powered, plugged in, logged into Windows, and connected to the internet.

The installer creates one startup entry for the current Windows account and starts
the hidden Tradysquids Supervisor immediately.

## Normal workflow after installation

1. Describe an upgrade or Discord change in ChatGPT.
2. The repository is updated.
3. The supervisor notices the new `main` commit within about two minutes.
4. It protects local runtime data, performs a fast-forward update, compiles the
   Python files, and runs the focused test suite.
5. It synchronizes Discord slash commands and runs
   `sync_discord_structure.py --apply`.
6. It restarts the command bot, information engine, and ngrok.
7. It posts deployment or rollback status to Discord.

No manual `git pull`, CMD-window closing, or BAT-file restart is required after
the one-time installation.

## Safety controls

- Updates are accepted only from `origin/main`.
- Non-fast-forward updates are rejected.
- Local runtime state is backed up and restored during deployment.
- Unknown local code changes block automatic deployment.
- Failed validation causes an automatic rollback.
- Discord changes are limited by the TradeBot role permissions.
- Secret values remain in the local `.env` and are never committed.

## Files and logs

- Supervisor state: `state/supervisor-state.json`
- Supervisor logs: `state/supervisor-logs/`
- Service logs: `state/supervisor-logs/command-bot.log`,
  `information-engine.log`, and `ngrok.log`

## Manual fallback

`START-TRADYSQUID.bat` now starts the background supervisor rather than opening
three permanent CMD windows.

To remove automatic startup, run `UNINSTALL-REMOTE-CONTROL.cmd`.
