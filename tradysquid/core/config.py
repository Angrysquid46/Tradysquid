from __future__ import annotations
import hashlib, json, os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SECRET_NAMES = {
    'DISCORD_BOT_TOKEN', 'DISCORD_GUILD_ID', 'DISCORD_OWNER_USER_ID',
    'TRADIER_ACCESS_TOKEN', 'TRADIER_ENVIRONMENT'
}
FORBIDDEN_LEGACY_NAMES = {
    'PC2_SHARED_TOKEN', 'PC2_BASE_URL', 'TRADYSQUID_PC2_SHARED_TOKEN',
    'X-Tradysquid-Token'
}

def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()

def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise ValueError(f'Required configuration file is missing: {path}') from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f'Configuration file is invalid JSON: {path}: {exc}') from exc
    if not isinstance(value, dict):
        raise ValueError(f'Configuration root must be an object: {path}')
    return value

def validate_strategy_config(config: dict[str, Any]) -> None:
    required = {'schema_version','strategy_id','version','enabled','play_style','direction','structure','preset','contract_filters','entry','management','learning'}
    missing = sorted(required - set(config))
    if missing:
        raise ValueError(f"Strategy {config.get('strategy_id','unknown')} missing fields: {', '.join(missing)}")
    risk = float(config['contract_filters'].get('maximum_risk_dollars', 0))
    if not 0 < risk <= 100:
        raise ValueError('maximum_risk_dollars must be greater than 0 and no more than 100')
    if config['preset'] not in {'loose','balanced','tight','profit-focused'}:
        raise ValueError('preset must be loose, balanced, tight, or profit-focused')
    if config['direction'] not in {'call','put'}:
        raise ValueError('direction must be call or put')
    if config['structure'] not in {'long-option','credit-spread'}:
        raise ValueError('structure must be long-option or credit-spread')

@dataclass(frozen=True)
class AppConfig:
    root: Path
    defaults: dict[str, Any]
    strategies: dict[str, dict[str, Any]]
    discord_schema: dict[str, Any]
    learning_center: dict[str, Any]
    presets: dict[str, dict[str, Any]]
    secrets_present: dict[str, bool]

    @classmethod
    def load(cls, root: Path) -> 'AppConfig':
        defaults = read_json(root / 'config' / 'defaults.json')
        if int(defaults.get('universe', {}).get('maximum_active', 0)) != 25:
            raise ValueError('universe.maximum_active must be 25')
        if float(defaults.get('risk', {}).get('maximum_position_risk_dollars', 0)) != 100.0:
            raise ValueError('risk.maximum_position_risk_dollars must be 100.0')
        presets = {path.stem: read_json(path) for path in sorted((root / 'config' / 'presets').glob('*.json'))}
        strategies: dict[str, dict[str, Any]] = {}
        for path in sorted((root / 'config' / 'strategies').glob('*.json')):
            config = read_json(path)
            validate_strategy_config(config)
            preset_name = str(config['preset'])
            preset = presets.get(preset_name, {}).get('overrides', {})
            config = json.loads(json.dumps(config))
            for key, value in preset.items():
                if key in config['contract_filters']:
                    config['contract_filters'][key] = value
                elif key in config['entry']:
                    config['entry'][key] = value
            sid = str(config['strategy_id'])
            if sid in strategies:
                raise ValueError(f'Duplicate strategy ID: {sid}')
            config = dict(config)
            config['configuration_hash'] = stable_hash({k:v for k,v in config.items() if k != 'configuration_hash'})
            strategies[sid] = config
        expected = {'regular-call','regular-put','swing-call','swing-put','bull-put-spread','bear-call-spread'}
        if set(strategies) != expected:
            raise ValueError(f'Strategy set must be exactly {sorted(expected)}')
        discord_schema = read_json(root / 'config' / 'discord-schema.json')
        learning_center = read_json(root / 'config' / 'learning-center.json')
        if len(learning_center.get('lessons', [])) != 27:
            raise ValueError('Learning Center must contain exactly 27 lessons')
        return cls(root, defaults, strategies, discord_schema, learning_center, presets,
                   {name: bool(os.environ.get(name)) for name in sorted(SECRET_NAMES)})

def redact(value: str) -> str:
    text = value
    for name in SECRET_NAMES | FORBIDDEN_LEGACY_NAMES:
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, '[REDACTED]')
    return text
