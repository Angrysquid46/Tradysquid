# Current requirements traceability

This rebuild treats the owner-approved clean-rebuild specification as the only product source. Old runtime code and databases are not imported.

| Requirement | Implementation | Configuration | Data | Tests | Live proof |
|---|---|---|---|---|---|
| Six independent option strategies | `tradysquid/strategies` | `config/strategies/*.json` | strategy tables | `tests/test_strategies.py` | registry acknowledgements |
| Rotating universe capped at 25 | `tradysquid/universe/service.py` | `config/defaults.json` | universe tables | `tests/test_universe.py` | universe receipt |
| $100 paper-risk ceiling | `tradysquid/trading/risk.py` | global and profile risk fields | candidate and fill records | `tests/test_risk_and_fills.py` | controlled rejection |
| Accepted, rejected, and shadow tracking | `tradysquid/scanner/service.py` | strategy selection mode | candidate and shadow tables | `tests/test_scanner.py` | controlled scan |
| Conservative paper lifecycle | `tradysquid/trading` | fill and management settings | paper position tables | `tests/test_paper_broker.py` | controlled cycles |
| Learning and recommendations | `tradysquid/learning` | learning settings | learning tables | `tests/test_learning.py` | Learning Results card |
| 27-channel Learning Center | `tradysquid/learning/center.py` | `config/learning-center.json` | version table | `tests/test_learning_center.py` | Discord channel count |
| Discord controls and reports | `tradysquid/discord` | `config/discord-schema.json` | message state tables | `tests/test_discord_contracts.py` | Discord acknowledgements |
| One process and one-click Windows setup | `tradysquid/app.py`, `scripts/*.ps1` | `.env`, defaults | runtime receipts | `tests/test_process_lock.py` | setup receipt |
| Safe update and rollback | `scripts/update.ps1`, `scripts/rollback.ps1` | repository remote | deployment receipts | contract tests | update/rollback receipt |

Live checks remain blocked until executed on the owner’s Windows computer with its private `.env` and Discord server.
