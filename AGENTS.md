# Tradysquid clean-rebuild maintainer contract

The clean-rebuild branch is a paper-trading-only system built for one Windows computer.

Before changing code:

1. Work on a separate branch.
2. Preserve unrelated owner configuration and runtime data.
3. Never commit `.env`, databases, logs, brokerage data, or private Discord content.
4. Do not add brokerage write methods, live order endpoints, second-computer dependencies, hardcoded ticker behavior, or automatic strategy changes.

Before merge:

1. Run `python -m compileall -q tradysquid scripts tests`.
2. Run `python -m pytest`.
3. Run the forbidden-endpoint and hardcoded-ticker searches.
4. Require CI success.
5. Distinguish code written, tests passed, merged, installed, and live verified.

Deployment must use the committed update and rollback scripts. A Discord card is not proof that the Windows installation is healthy.
