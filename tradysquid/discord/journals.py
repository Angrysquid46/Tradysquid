from __future__ import annotations
import json
from .contracts import split_text

class JournalService:
    def __init__(self, database):
        self.db = database

    def render(self, position_id: str) -> list[str]:
        positions = self.db.query('SELECT * FROM paper_positions WHERE id=?', (position_id,))
        if not positions:
            raise KeyError(position_id)
        p = positions[0]
        legs = self.db.query('SELECT * FROM paper_legs WHERE position_id=? ORDER BY id', (position_id,))
        events = self.db.query('SELECT * FROM lifecycle_events WHERE position_id=? ORDER BY observed_at', (position_id,))
        config = json.loads(p['config_json'])
        lines = [
            f"# Trade Journal {position_id}",
            f"**Symbol:** {p['symbol']}",
            f"**Strategy:** {p['strategy_id']} @ {p['strategy_version']}",
            f"**Configuration hash:** {p['strategy_hash']}",
            f"**Direction / structure:** {p['direction']} / {p['structure']}",
            f"**State:** {p['state']}",
            f"**Opened:** {p['opened_at']}",
            f"**Entry value:** ${p['entry_value']:.2f}",
            f"**Maximum risk:** ${p['maximum_risk']:.2f}",
            f"**Current P/L:** ${p['pnl_dollars']:.2f} ({p['pnl_pct']:.2%})",
            f"**MFE / MAE:** {p['mfe_pct']:.2%} / {p['mae_pct']:.2%}",
            '', '## Option legs',
        ]
        for leg in legs:
            lines.append(f"- {leg['side']} {leg['quantity']} {leg['option_type']} {leg['strike']} {leg['expiration']} | entry {leg['entry_fill']:.2f} | mark {leg['current_mark']:.2f}")
        lines += ['', '## Entry plan',
                  f"- Profit target: {config['management']['profit_target_pct']:.2%}",
                  f"- Hard stop: {config['management']['hard_stop_pct']:.2%}",
                  '- Evidence and thesis remain attached to the candidate record and are not rewritten after outcome.',
                  '', '## Lifecycle']
        for event in events:
            lines.append(f"- {event['observed_at']} | {event['previous_state'] or 'NONE'} -> {event['new_state']} | {event['reason']}")
        return split_text('\n'.join(lines))
