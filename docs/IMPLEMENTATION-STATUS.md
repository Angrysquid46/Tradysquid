# Implementation status

## Written and locally tested

- Replacement source tree with no copied legacy application modules
- Single-computer, one-process application ownership
- Exact six-strategy registry
- Versioned owner-approved strategy changes, rollback, and runtime acknowledgements
- Distinct loose, balanced, tight, and profit-focused presets
- $100 paper-risk calculation for long options and defined-risk credit spreads
- Ticker-agnostic Tradier ETB universe discovery capped at 25 active symbols
- Owner universe add/remove/pin/exclude controls with open-position protection
- Central read-only Tradier request manager
- Regime classification and multi-field candidate decisions
- Accepted, rejected, selected, and shadow records
- Conservative paper fills, lifecycle state, configured management evaluation, MFE, MAE, and closed outcomes
- SQLite WAL schema, integrity check, backup support, canonical period/ticker/strategy reporting, and reconciliation
- Learning metrics, rejection tradeoffs, and owner-reviewed recommendations
- Declarative Discord structure, owner commands, journals, report rendering, and non-destructive message reconciliation
- Exactly 27 Learning Center lessons
- Scheduler execution receipts and stable diagnostic fingerprints
- Windows setup, credential whitelist, live preflight, startup receipt, start, stop, update, and rollback entrypoints
- CI workflow and 51 passing local automated tests

## Blocked pending the production Windows computer

- Annotated Git tag creation
- OneDrive coordination-lock inspection
- Local legacy runtime backup and cleanup
- Private `.env` credential preservation
- Tradier live read-only acceptance
- Discord authentication, channel synchronization, command registration, journals, and reports
- Windows scheduled startup
- Real updater and rollback acceptance

No blocked item is represented as passed.
