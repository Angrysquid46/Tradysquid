from __future__ import annotations
import json, os
from pathlib import Path
import requests
from dotenv import load_dotenv
from tradysquid.app import Application

root = Path(__file__).resolve().parents[1]
load_dotenv(root / '.env', override=True)
required = ['DISCORD_BOT_TOKEN','DISCORD_GUILD_ID','DISCORD_OWNER_USER_ID','TRADIER_ACCESS_TOKEN','TRADIER_ENVIRONMENT']
missing = [name for name in required if not os.environ.get(name)]
if missing:
    raise SystemExit('FAILED: missing required variable names: ' + ', '.join(missing))

app = Application(root)
clock = app.provider.market_clock()
if not clock:
    raise SystemExit('FAILED: Tradier market clock returned no data')
active = app.initialize_universe()
if not active:
    raise SystemExit('FAILED: no optionable universe symbols were discovered')
decisions = app.scanner.scan_symbol(active[0], 'setup-acceptance')
if len(decisions) != 6:
    raise SystemExit(f'FAILED: expected six strategy decisions, got {len(decisions)}')

headers = {'Authorization': 'Bot ' + os.environ['DISCORD_BOT_TOKEN'], 'User-Agent': 'Tradysquid/0.1'}
user = requests.get('https://discord.com/api/v10/users/@me', headers=headers, timeout=(5, 20))
if user.status_code != 200:
    raise SystemExit(f'FAILED: Discord authentication returned HTTP {user.status_code}')
guild = requests.get('https://discord.com/api/v10/guilds/' + os.environ['DISCORD_GUILD_ID'], headers=headers, timeout=(5, 20))
if guild.status_code != 200:
    raise SystemExit(f'FAILED: Discord guild access returned HTTP {guild.status_code}')

receipt = {
    'status': 'PASS',
    'tradier_clock': True,
    'universe_count': len(active),
    'controlled_symbol': active[0],
    'strategy_decisions': len(decisions),
    'discord_bot_id': user.json().get('id'),
    'discord_guild_id': guild.json().get('id'),
}
(root / 'state').mkdir(exist_ok=True)
(root / 'state' / 'live-preflight.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
print(json.dumps(receipt, sort_keys=True))
