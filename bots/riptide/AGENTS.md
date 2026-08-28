# Scoped instructions - bots/riptide

RIPTIDE is a Codex-owned, paper-only private challenger. It may read only
neutral shared market facts, the neutral scorekeeper, and its own state. It
must never import, inspect, or use either `bots/blacktide` or `bots/claude`.

Hard limits: SPY long 0DTE calls/puts, $1,000 starting bankroll per
generation, one open paper position, causal observed data, realistic ask-entry
and bid-exit accounting, immutable official closes, and no brokerage orders.
