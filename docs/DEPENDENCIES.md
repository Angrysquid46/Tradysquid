# Dependencies

| Package | Version | Purpose | Scope | License/security note |
|---|---:|---|---|---|
| APScheduler | 3.10.4 | In-process scheduled jobs | Runtime | BSD-style; pinned |
| discord.py | 2.4.0 | Outbound Discord bot connection | Runtime | MIT; pinned |
| python-dotenv | 1.0.1 | Local secret loading | Runtime | BSD-style; pinned |
| requests | 2.32.3 | Read-only Tradier HTTP client | Runtime | Apache-2.0; pinned |
| pytest | 8.3.4 | Automated tests | Development | MIT; pinned |
| pytest-cov | 6.0.0 | Coverage support | Development | MIT; pinned |

The setup script runs `pip check`. A future connected CI runner should also run `pip-audit`; the application does not pretend that a dependency is safe merely because a table says so.
