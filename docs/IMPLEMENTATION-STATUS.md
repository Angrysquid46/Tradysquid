# Implementation status

## Written and locally tested

- Replacement source tree with no copied legacy application modules
- Single-computer, one-process application ownership
- Exact six-strategy registry
- Versioned strategy configuration and distinct presets
- $100 paper-risk calculation for long options and defined-risk credit spreads
- Ticker-agnostic Tradier ETB universe discovery capped at 25 active symbols
- Central read-only Tradier request manager
- Regime classification and multi-field candidate decisions
- Accepted, rejected, and shadow records
- Conservative paper fills, lifecycle state, MFE, MAE, and closed outcomes
- SQLite WAL schema, integrity check, backup support, and canonical reporting
- Learning metrics and owner-reviewed recommendations
- Declarative Discord structure, commands, and non-destructive message reconciliation
- Exactly 27 Learning Center lessons
- Windows setup, start, stop, update, and rollback entrypoints
- CI workflow and 32 local automated tests

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
