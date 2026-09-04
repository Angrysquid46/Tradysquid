# Scoped instructions - bots/grok

GROK is a Grok/xAI-designed, paper-only private competitor. The owner supplies
or approves GROK's strategy concept; Codex is the master implementation editor
responsible for turning that concept into tested, live code. Grok and Codex may
read and write this directory. Neither may consume another trader's private
strategy.

It may read neutral shared market facts, the scorekeeper, and its own state only.
It must never import, inspect, infer, copy, or train from BLACKTIDE, RIPTIDE, or SURGE private strategy intelligence.

Hard limits (immutable competition rules):
- SPY long 0DTE calls and puts only (BTO → STC)
- $1,000 starting bankroll every generation
- Maximum one official open trade at a time
- Observed ASK for entry, observed BID for exit
- No lookahead, no invented data, no hidden portfolios
- Neutral referee is the sole official ledger
- Bust → freeze generation, preserve history, postmortem, reset to $1,000, next generation

Strategy privacy is absolute. Official public surfaces expose only factual scoreboard data.
