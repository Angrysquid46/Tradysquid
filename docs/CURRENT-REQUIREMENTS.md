# Current requirements traceability

This document reflects the owner-approved runtime after the August 3, 2026
Discord-layout and full-audit corrections. Repository tests prove code behavior;
only a receipt from the owner computer can prove live deployment.

| Requirement | Implementation | Configuration / data | Automated proof | Live proof |
|---|---|---|---|---|
| Exactly six independent option strategies | `tradysquid/strategies`, `config/strategies/*.json` | strategy profiles, versions, acknowledgements | strategy and installation tests | running registry receipt |
| Rotating optionable universe, maximum 25 | `tradysquid/universe` | `config/defaults.json`, universe tables | universe tests | active-universe receipt/card |
| Global maximum $100 paper risk | `tradysquid/trading/risk.py` | strategy filters and defaults | risk/fill tests | controlled rejection |
| Accepted and rejected candidate tracking | `tradysquid/scanner` | candidate/evidence/rejection tables | scanner tests | current scan receipt |
| No shadow-trading feature | no active shadow command, route, scheduler job, status, table, or renderer | obsolete bot-authored message/channel cleanup only | full-audit regression tests | retired-message cleanup receipt |
| Automatic paper-entry modes actually open selected candidates | `Application.scan_symbol`, `PaperBroker.open` | versioned `entry.selection_mode` | full-audit regression tests | paper-entry lifecycle receipt |
| Stops and targets actually close positions | `Application.monitor_positions`, `PaperBroker.mark/close` | position marks, closed outcomes, lifecycle events | paper lifecycle tests | closed outcome and journal |
| Existing legacy closed paper trades are preserved | `tradysquid/data/legacy_import.py` | ignored `state/spy-plays-log.csv` to canonical SQLite ledger | idempotent importer tests | import receipt and historical cards |
| Original Discord dashboard plus Strategy Control | `tradysquid/discord/layout.py`, `structure.py` | `config/discord-schema.json`, saved channel IDs | Discord layout tests | Discord readiness receipt |
| No SCANNING, PAPER TRADING, or LEARNING CENTER 2 dashboard | safe migration cleanup in `structure.py` | cleanup receipts | migration tests | live cleanup receipt |
| Stable readable cards update in place | publishing and message reconciliation | Discord message state | publishing tests | acknowledged message IDs |
| One Learning Center with 27 numbered lessons | learning catalog and original channel mapping | `config/learning-center.json` | Learning Center tests | extended backfill receipt |
| One stable Trade Journal thread per paper position | `discord/journals.py`, forum reconciliation | journal state | journal tests | extended backfill receipt |
| Closed trades populate Wins, Losses, Performance, and Learning | canonical `closed_outcomes` queries | SQLite ledger | historical-card regression tests | Discord card acknowledgements |
| Core startup does not wait for every historical journal | core bootstrap plus asynchronous extended backfill | core and extended receipts | bootstrap contract tests | both live receipts |
| Scanning and position monitoring begin immediately during regular market hours | scheduler startup jobs plus cached Tradier market clock | scheduler receipts | scheduler and operational audit tests | recent scheduler runs |
| Provider load remains below the shared minute budget | rotating batches of at most eight symbols, 25-request reserve, grouped position chains | persisted scan cursor and request ledger | operational audit tests | live provider-budget receipt |
| Paper risk uses conservative executable fills | `PaperBroker.open` | stored leg fills and actual maximum risk | paper-fill regression tests | opened-position ledger |
| Complete `.env`, data, state, and logs survive handoff | automatic handoff and setup scripts | external backup | installer contract tests | handoff receipt |
| Rollback restores prior scheduled tasks | `auto_install_clean_rebuild.ps1` | task XML backup | PowerShell contract test | rollback receipt plus task inventory |
| Read-only Tradier only | `tradysquid/providers/tradier.py` | market-data endpoints | forbidden-write tests | provider readiness |
| One Windows application PID | process lock and startup task | PID/startup receipts | process-lock tests | exactly-one-process acceptance |

## Current deployment boundary

The tested target is not considered installed merely because GitHub CI passes.
Live completion requires the owner computer to produce current PASS receipts for
automatic handoff, setup, application startup, Discord core readiness, and the
extended Discord backfill.
