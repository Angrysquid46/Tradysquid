# Tradysquid clean rebuild

Tradysquid is a single-computer, paper-only options research system. It scans a rotating universe of up to 25 configurable symbols, evaluates six independent strategies, records every accepted and rejected decision, tracks conservative paper positions and shadow candidates, produces learning statistics, and publishes owner-controlled Discord views.

## Safety

- No brokerage order methods or write endpoints exist.
- Tradier is used only for read-only market data.
- The default maximum paper risk per position is $100.
- Strategy recommendations never change active settings without owner approval.
- No second computer, LAN service, ngrok tunnel, Docker service, Redis server, or paid AI API is required.

## Owner setup

Double-click `SETUP-AND-START.cmd`. The installer preserves recognized local secrets, creates the virtual environment and database, runs tests, validates read-only services, registers startup, and starts one application process.

## Development

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```
