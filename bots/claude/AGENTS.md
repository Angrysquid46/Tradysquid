# Scoped instructions - bots/claude (CLAUDE_ONLY)

Read this alongside the root `AGENTS.md`, per its nearest-scoped-file
convention. This file is a human/agent-readable restatement, not a grant
in itself - `governance/OWNERSHIP.json`'s `"bots/claude/"` entry
(`writers: ["Claude"]`) is the authoritative, machine-enforced grant,
checked by `ai_coordination.py`'s `enforce_ownership()` on every `finish()`.

## Ownership

- Everything under this directory is `CLAUDE_ONLY` (Master Spec Section
  11).
- Only Claude may write here. Codex must not modify or consume
  Claude-private strategy intelligence (Section 3's private-competitor
  boundary, mirrored the other direction from `bots/blacktide/`).
- Private here means: entries, exits, learned thresholds/weights, private
  models, private research conclusions, private evolution logic, future
  trade reasoning, and opponent postmortem intelligence
  (`governance/IMMUTABLE_RULES.json`'s `private_resources_include`).
- Shared, non-private resources both competitors may use live outside
  this directory: SPY/option observations, calendars, factual event
  timestamps, deterministic neutral features, the backtest engine,
  execution simulator, data-quality infrastructure, API manager, market
  cache, neutral scorekeeper, Discord transport.

## What this directory is for

Claude's private trader, **AXIOM** (competitor identity "AXIOM" in
`governance/IMMUTABLE_RULES.json`'s `competitors` block; this directory
and the `"Claude"` writer/actor identity are unchanged - a separate,
engineering-agent namespace), built here in Phase 13, under Section 4's
immutable competition rules (SPY options only, long 0DTE calls/puts to
start, $1,000 starting bankroll per generation, one open trade at a
time, no lookahead, no live shadow trading, completed trades immutable,
bust protocol resets bankroll and preserves history). AXIOM was
independently designed from scratch - not a copy of, derived from, or
informed by BLACKTIDE's private strategy; `bots/blacktide/` was never
read while designing it. Modules: `parameters.py` (every tunable
threshold, named), `signal.py` (entry decision), `contract_selection.py`,
`sizing.py`, `execution.py` (fill model), `exits.py`, `backtest_runner.py`,
`scheduler.py`/`runtime.py` (live loop), `postmortems/` (bust records).
