# Tradysquid Free Resource Mesh

This upgrade uses one optional second Windows PC without turning it into a second
production scanner. The production PC remains the sole owner of Tradier,
Discord, trade state, deployment, and the live position stream. The worker PC
handles free-data collection, background computation, dependency/security
checks, and optional self-hosted GitHub Actions.

No second PC is required for correctness. If the worker is off, the production
PC claims pending tasks through a low-priority local fallback. When the worker
returns, its heartbeat takes ownership again automatically.

## What the upgrade adds

- Shared cross-process Tradier budget based on the live rate-limit headers.
- Default allowance of 125 requests per minute with a two-request position-safety reserve.
- SQLite response cache shared by the command bot, scanner, information engine, and manual tools.
- Daily-history and expiration reuse instead of downloading the same data repeatedly.
- Option strikes derived from the returned chain instead of a separate strike-list request.
- Priority provider lanes so position protection outranks scanning, news, charts, and reporting.
- TradingView/provider events routed to a durable targeted-scan queue instead of waiting for the normal rotation.
- Atomic JSON file spool for one optional second PC.
- Local fallback when the worker PC is unavailable.
- Free-data enrichment from SEC, Cboe, BLS, ClinicalTrials.gov, Federal Register, GDELT, and Treasury Fiscal Data without paid credentials.
- Optional free-key enrichment from Finnhub, Twelve Data, Alpha Vantage, FRED, BLS registered access, and EIA.
- Upcoming earnings written to the event-risk file and attached to new paper-trade evidence as a binary-event warning.
- Ruff, pre-commit, pip-audit, secret hygiene, Dependabot, and an optional self-hosted quality workflow.

## Production PC setup

Do this only after the branch is reviewed, merged, deployed, and its ordinary
runtime tests pass.

Open **Administrator PowerShell** in the repository and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\SETUP-RESOURCE-MESH-SHARE.ps1
```

The script:

1. Creates `C:\TradysquidMesh`.
2. Creates a dedicated local Windows account named `TradysquidWorker`.
3. Prompts for that account's password.
4. Grants only that account modify access to the mesh.
5. Creates an authenticated SMB share named `TradysquidMesh`.
6. Writes `RESOURCE_MESH_ROOT=C:\TradysquidMesh` to the production `.env`.
7. Leaves `RESOURCE_MESH_LOCAL_FALLBACK=true` so production keeps working if PC 2 is offline.

Record the two values printed at the end:

```text
Worker UNC path: \\PRIMARY-PC\TradysquidMesh
Worker account: PRIMARY-PC\TradysquidWorker
```

Do not put the Tradier token, Discord token, GitHub deployment token, ngrok
token, or OpenAI key in the shared folder.

## Worker PC setup

Clone the repository to PC 2 after the resource-mesh upgrade is merged and
deployed. Open ordinary PowerShell in that clone and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\SETUP-RESOURCE-WORKER.ps1 `
  -MeshRoot "\\PRIMARY-PC\TradysquidMesh" `
  -ShareUser "PRIMARY-PC\TradysquidWorker"
```

The script:

1. Saves the share credential in Windows Credential Manager for the current user.
2. Verifies read/write access to the mesh.
3. Creates an isolated `.venv-worker`.
4. Installs only `requests` and `tzdata`.
5. Creates `.env.worker` from `.env.worker.example`.
6. Runs one worker self-test.
7. Creates and starts the **Tradysquid Resource Worker** scheduled task.
8. Restarts the worker one minute after an unexpected exit.

The worker starts automatically at Windows logon. It does not need production
credentials.

## Free provider keys

The worker immediately uses the no-key sources. Add every optional free key to
`.env.worker` when available. Missing keys are marked `SKIPPED`; they do not
break the worker or scanner.

| Source | Cost | Used for | Configuration |
|---|---:|---|---|
| SEC EDGAR | Free, no API key | Filings, company facts, ticker/CIK mapping | `SEC_USER_AGENT` with a real contact |
| Cboe public CSV | Free, no API key | VIX and VVIX context | None |
| BLS public API | Free, no key required | CPI, payrolls, unemployment | Optional `BLS_API_KEY` increases quota |
| ClinicalTrials.gov API v2 | Free, no API key | Sponsor trial changes for life-science companies | None |
| Federal Register API | Free, no API key | Regulatory mentions and documents | None |
| GDELT DOC API | Free public endpoint | Broad news discovery and coverage changes | None |
| Treasury Fiscal Data API | Free, no API key | Treasury average-interest-rate context | None |
| Finnhub | Free account | Profile, quote cross-check, company news, earnings calendar | `FINNHUB_API_KEY` |
| Twelve Data Basic | Free account | Press releases and secondary market context | `TWELVE_DATA_API_KEY` |
| Alpha Vantage | Free account | Company overview/fundamental cross-check | `ALPHA_VANTAGE_API_KEY` |
| FRED | Free account | Rates, spreads, credit, inflation, labor, VIX | `FRED_API_KEY` |
| EIA | Free account | Oil, natural gas, energy, macro data | `EIA_API_KEY` |

Registration pages:

- Finnhub: https://finnhub.io/register
- Twelve Data: https://twelvedata.com/register
- Alpha Vantage: https://www.alphavantage.co/support/#api-key
- FRED: https://fred.stlouisfed.org/docs/api/api_key.html
- BLS: https://data.bls.gov/registrationEngine/
- EIA: https://www.eia.gov/opendata/register.php

The worker applies the published free ceilings and then obeys real HTTP 429
responses. It does not invent a lower quota merely to feel virtuous.

## Tradier behavior

`market_data_runtime.py` writes every local Tradier process into one SQLite
ledger. The configured value is only the startup assumption. Every Tradier
response can replace it with the live values from:

- `X-Ratelimit-Allowed`
- `X-Ratelimit-Used`
- `X-Ratelimit-Available`
- `X-Ratelimit-Expiry`

The runtime therefore follows the account's real allowance even when the public
documentation or account tier changes.

Only two calls are reserved at the end of the window for position protection.
The targeted scanner defers when the available count is too low to complete a
safe one- or two-symbol scan, then resumes after reset. Live position quotes do
not use stale cache values.

## Targeted scans

The following events can enter the targeted queue:

- TradingView events.
- High-priority provider events.
- Discord member universe changes.
- Read-only Robinhood discovery events.

Defaults:

```env
TARGETED_SCAN_ENABLED=true
TARGETED_SCAN_MIN_EVENT_PRIORITY=75
TARGETED_SCAN_COOLDOWN_SECONDS=60
TARGETED_SCAN_MAX_SYMBOLS=2
TARGETED_SCAN_MIN_TRADIER_AVAILABLE=12
```

The ordinary rotating scan remains active as the fallback. Targeted scans do
not remove tickers, change strategy profiles, place orders, or bypass risk
filters.

## Resource files

Production status files:

```text
state/tradier-resource-status.json
state/provider-lanes.json
state/targeted-scan-status.json
state/resource-mesh-status.json
state/event-risk.json
state/macro-context.json
state/resource-enrichment/<TICKER>.json
```

Shared mesh folders:

```text
inbox/       pending atomic tasks
processing/  tasks claimed by one worker
outbox/      successful results waiting for production
failed/      failed or expired tasks
archive/     results already consumed by production
dedupe/      idempotency markers
cache/       worker-safe public-data cache
```

## Optional self-hosted GitHub runner

PC 2 can also run the resource-mesh quality workflow without consuming a hosted
runner. In the GitHub repository, open:

```text
Settings > Actions > Runners > New self-hosted runner > Windows > x64
```

Copy the short-lived registration token, then run **Administrator PowerShell**:

```powershell
powershell -ExecutionPolicy Bypass -File .\SETUP-SELF-HOSTED-RUNNER.ps1 `
  -RegistrationToken "PASTE-THE-SHORT-LIVED-TOKEN"
```

The installer downloads the latest official Windows x64 runner from the GitHub
`actions/runner` release, adds the `tradysquid-worker` label, and installs it as
an auto-start Windows service. The registration token is not written to disk by
the script.

The workflow runs:

- Python compilation.
- Secret/runtime-state hygiene.
- Ruff lint and formatting checks.
- Resource-mesh unit tests.
- `pip-audit` on production and worker requirements.

## Local quality tools

On either trusted development PC:

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALL-FREE-QUALITY-TOOLS.ps1
```

This creates `.venv-dev`, installs Ruff, pre-commit, and pip-audit, installs the
pre-commit hook, then runs the first complete check.

## Failure behavior

- Worker PC off: production local fallback processes tasks at low priority.
- Shared folder unavailable: tasks stop moving, while Tradier scanning and open-position management continue.
- Optional API key missing: that provider is skipped.
- Optional provider returns 429: the worker backs off and records the error.
- Optional provider is down: other providers continue.
- Tradier budget exhausted: discovery waits for reset; open-position protection retains priority.
- Malformed result file: moved to failed processing and surfaced in health state.
- Duplicate event: deduplicated by stable key and cooldown bucket.
- Production restart: SQLite and file-spool state survive.
- Worker restart: unclaimed tasks remain in the inbox.

## Removal

Remove the worker task while preserving shared data:

```powershell
powershell -ExecutionPolicy Bypass -File .\REMOVE-RESOURCE-WORKER.ps1 `
  -ShareHost "PRIMARY-PC"
```

Add `-RemoveVirtualEnvironment` and `-RemoveWorkerEnvironment` only when those
local worker files should also be deleted.

## Acceptance checklist

Before production activation, require all of the following:

1. Existing strategy-runtime PR tests pass.
2. Resource modules compile.
3. Resource unit tests pass.
4. Secret hygiene passes.
5. `pip-audit` results are reviewed.
6. Production starts with the worker absent and local fallback healthy.
7. A test task completes locally.
8. The worker is installed and its heartbeat becomes current.
9. A test task completes on PC 2.
10. Turning off PC 2 returns ownership to local fallback.
11. Tradier status shows the actual live header allowance.
12. A synthetic TradingView event produces one targeted scan without duplicate paper trades.
13. Open-position tracking remains higher priority than every background lane.
14. No production secret exists in the shared folder or worker `.env.worker`.

This document describes the implementation branch. Creating the files is not
proof of merge, deployment, installation, or live acceptance.
