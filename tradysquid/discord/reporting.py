from __future__ import annotations
import json

class DiscordReportRenderer:
    def render_metrics(self, title: str, metrics: dict) -> dict:
        fields = [
            {'name': 'Sample', 'value': f"{metrics.get('sample_size',0)} | {metrics.get('sample_label','')}", 'inline': False},
            {'name': 'Wins / losses', 'value': f"{metrics.get('wins',0)} / {metrics.get('losses',0)}", 'inline': True},
            {'name': 'Win rate', 'value': f"{metrics.get('win_rate',0):.2%}", 'inline': True},
            {'name': 'Net paper P/L', 'value': f"${metrics.get('net_pnl',0):.2f}", 'inline': True},
            {'name': 'Expectancy', 'value': f"${metrics.get('expectancy',0):.2f}", 'inline': True},
            {'name': 'Profit factor', 'value': str(metrics.get('profit_factor',0)), 'inline': True},
            {'name': 'Maximum drawdown', 'value': f"${metrics.get('maximum_drawdown',0):.2f}", 'inline': True},
        ]
        return {'embeds': [{'title': title, 'description': 'Paper-trading results only. Percentages always include their sample count.', 'fields': fields}]}
