# Scoped instructions - bots/blacktide (BLACKTIDE_ONLY)

Read this alongside the root `AGENTS.md`, per its nearest-scoped-file
convention. This file is a human/agent-readable restatement, not a grant
in itself - `governance/OWNERSHIP.json`'s `"bots/blacktide/"` entry
(`writers: ["Codex"]`) is the authoritative, machine-enforced grant,
checked by `ai_coordination.py`'s `enforce_ownership()` on every `finish()`.

## Ownership

- Everything under this directory is `BLACKTIDE_ONLY` (Master Spec
  Section 11).
- Only Codex may write here. Claude must not write, and per Section 3's
  private-competitor boundary must not **request, inspect, infer, copy,
  modify, or train from** anything BLACKTIDE-private - not just avoid
  editing it.
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

BLACKTIDE (`BLACKTIDE_SPY`, "Autonomous SPY Options Evolution Engine") is
built here in Phase 12, under Section 4's immutable competition rules
(SPY options only, long 0DTE calls/puts to start, $1,000 starting
bankroll per generation, one open trade at a time, no lookahead, no live
shadow trading, completed trades immutable, bust protocol resets
bankroll and preserves history). Nothing here yet - this phase (11) only
establishes the ownership boundary before either trader is implemented.
