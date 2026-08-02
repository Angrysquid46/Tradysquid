"""Versioned, read-only strategy profile foundation.

PR 1 deliberately does not change scanner or position-management behavior. It
captures the currently active rules in one validated schema so later chunks can
consume, edit, version, and acknowledge them without touching deployment code.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT / "config" / "strategy_profiles.json"
DEFAULT_RUNTIME_STATE_PATH = ROOT / "state" / "strategy-runtime.json"
SCHEMA_VERSION = 1

PROFILE_IDENTITIES: dict[str, tuple[str, str, str]] = {
    "regular-call": ("REGULAR", "call", "long-option"),
    "regular-put": ("REGULAR", "put", "long-option"),
    "swing-call": ("SWING", "call", "long-option"),
    "swing-put": ("SWING", "put", "long-option"),
    "bull-put-spread": ("SPREAD", "put", "credit-spread"),
    "bear-call-spread": ("SPREAD", "call", "credit-spread"),
}


class StrategyProfileError(ValueError):
    """Raised when the stored strategy profile document is invalid."""


def _number(value: Any, path: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StrategyProfileError(f"{path} must be numeric")
    result = float(value)
    if minimum is not None and result < minimum:
        raise StrategyProfileError(f"{path} must be at least {minimum}")
    return result


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StrategyProfileError(f"{path} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise StrategyProfileError(f"{path} must be a list of non-empty strings")
    return [item.strip() for item in value]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def configuration_hash(profile: dict[str, Any]) -> str:
    """Stable hash for exact stored settings, excluding runtime acknowledgement."""
    return hashlib.sha256(canonical_json(profile).encode("utf-8")).hexdigest()[:16]


def _validate_contract_filters(name: str, profile: dict[str, Any]) -> None:
    filters = profile.get("contract_filters")
    if not isinstance(filters, dict):
        raise StrategyProfileError(
            f"profiles.{name}.contract_filters must be an object"
        )
    dte_min = _number(
        filters.get("dte_min"),
        f"profiles.{name}.contract_filters.dte_min",
        minimum=0,
    )
    dte_max = _number(
        filters.get("dte_max"),
        f"profiles.{name}.contract_filters.dte_max",
        minimum=0,
    )
    if dte_min > dte_max:
        raise StrategyProfileError(f"profiles.{name} DTE minimum exceeds maximum")
    _number(
        filters.get("min_open_interest"),
        f"profiles.{name}.contract_filters.min_open_interest",
        minimum=0,
    )
    _number(
        filters.get("min_option_volume"),
        f"profiles.{name}.contract_filters.min_option_volume",
        minimum=0,
    )
    bid_ask = _number(
        filters.get("max_bid_ask_pct"),
        f"profiles.{name}.contract_filters.max_bid_ask_pct",
        minimum=0,
    )
    if bid_ask > 1:
        raise StrategyProfileError(
            f"profiles.{name}.contract_filters.max_bid_ask_pct cannot exceed 1"
        )
    _number(
        filters.get("max_position_risk_dollars"),
        f"profiles.{name}.contract_filters.max_position_risk_dollars",
        minimum=0.01,
    )
    _number(
        filters.get("reentry_cooldown_minutes"),
        f"profiles.{name}.contract_filters.reentry_cooldown_minutes",
        minimum=0,
    )

    if profile["structure"] == "long-option":
        delta_min = _number(
            filters.get("delta_min"),
            f"profiles.{name}.contract_filters.delta_min",
            minimum=0,
        )
        delta_max = _number(
            filters.get("delta_max"),
            f"profiles.{name}.contract_filters.delta_max",
            minimum=0,
        )
        if delta_min > delta_max or delta_max > 1:
            raise StrategyProfileError(f"profiles.{name} has an invalid delta range")
        _number(
            filters.get("max_contract_ask"),
            f"profiles.{name}.contract_filters.max_contract_ask",
            minimum=0.01,
        )
    else:
        delta_min = _number(
            filters.get("short_delta_min"),
            f"profiles.{name}.contract_filters.short_delta_min",
            minimum=0,
        )
        delta_max = _number(
            filters.get("short_delta_max"),
            f"profiles.{name}.contract_filters.short_delta_max",
            minimum=0,
        )
        if delta_min > delta_max or delta_max > 1:
            raise StrategyProfileError(
                f"profiles.{name} has an invalid short-leg delta range"
            )
        _number(
            filters.get("min_credit"),
            f"profiles.{name}.contract_filters.min_credit",
            minimum=0.01,
        )


def _validate_entry(name: str, profile: dict[str, Any]) -> None:
    entry = profile.get("entry")
    if not isinstance(entry, dict):
        raise StrategyProfileError(f"profiles.{name}.entry must be an object")
    _nonempty_string(entry.get("timeframe"), f"profiles.{name}.entry.timeframe")
    _string_list(
        entry.get("higher_timeframes"),
        f"profiles.{name}.entry.higher_timeframes",
    )
    rules = entry.get("rules")
    if not isinstance(rules, list) or not rules:
        raise StrategyProfileError(
            f"profiles.{name}.entry.rules must contain at least one rule"
        )
    rule_ids: set[str] = set()
    for index, rule in enumerate(rules):
        path = f"profiles.{name}.entry.rules[{index}]"
        if not isinstance(rule, dict):
            raise StrategyProfileError(f"{path} must be an object")
        rule_id = _nonempty_string(rule.get("id"), f"{path}.id")
        if rule_id in rule_ids:
            raise StrategyProfileError(
                f"profiles.{name} contains duplicate rule id {rule_id}"
            )
        rule_ids.add(rule_id)
        if not isinstance(rule.get("enabled"), bool):
            raise StrategyProfileError(f"{path}.enabled must be boolean")
        _nonempty_string(rule.get("type"), f"{path}.type")
        _nonempty_string(rule.get("action"), f"{path}.action")
        if not isinstance(rule.get("parameters"), dict):
            raise StrategyProfileError(f"{path}.parameters must be an object")

    groups = entry.get("rule_groups")
    if not isinstance(groups, list) or not groups:
        raise StrategyProfileError(
            f"profiles.{name}.entry.rule_groups must contain at least one group"
        )
    for index, group in enumerate(groups):
        path = f"profiles.{name}.entry.rule_groups[{index}]"
        if not isinstance(group, dict):
            raise StrategyProfileError(f"{path} must be an object")
        _nonempty_string(group.get("id"), f"{path}.id")
        operator = _nonempty_string(
            group.get("operator"), f"{path}.operator"
        ).upper()
        if operator not in {"ALL", "ANY", "AT_LEAST"}:
            raise StrategyProfileError(f"{path}.operator is unsupported")
        members = _string_list(group.get("rule_ids"), f"{path}.rule_ids")
        missing = sorted(set(members) - rule_ids)
        if missing:
            raise StrategyProfileError(
                f"{path} references unknown rules: {', '.join(missing)}"
            )
        if operator == "AT_LEAST":
            count = _number(
                group.get("minimum_matches"),
                f"{path}.minimum_matches",
                minimum=1,
            )
            if count > len(members):
                raise StrategyProfileError(
                    f"{path}.minimum_matches exceeds member count"
                )


def _validate_management(name: str, profile: dict[str, Any]) -> None:
    management = profile.get("management")
    if not isinstance(management, dict):
        raise StrategyProfileError(f"profiles.{name}.management must be an object")
    _nonempty_string(
        management.get("timeframe"), f"profiles.{name}.management.timeframe"
    )
    _number(
        management.get("poll_seconds"),
        f"profiles.{name}.management.poll_seconds",
        minimum=1,
    )
    for key in (
        "track_mfe",
        "track_mae",
        "dynamic_profit_protection_enabled",
        "technical_exit_enabled",
        "momentum_exit_enabled",
        "thesis_invalidation_enforced",
    ):
        if not isinstance(management.get(key), bool):
            raise StrategyProfileError(
                f"profiles.{name}.management.{key} must be boolean"
            )


def _validate_exit(name: str, profile: dict[str, Any]) -> None:
    exit_config = profile.get("exit")
    if not isinstance(exit_config, dict):
        raise StrategyProfileError(f"profiles.{name}.exit must be an object")
    for key in ("hard_stop", "profit_target", "expiration"):
        rule = exit_config.get(key)
        if not isinstance(rule, dict) or not isinstance(rule.get("enabled"), bool):
            raise StrategyProfileError(
                f"profiles.{name}.exit.{key} must be a rule object"
            )
        _nonempty_string(rule.get("type"), f"profiles.{name}.exit.{key}.type")
    _number(
        exit_config["hard_stop"].get("value"),
        f"profiles.{name}.exit.hard_stop.value",
        minimum=0.01,
    )
    _number(
        exit_config["profit_target"].get("value"),
        f"profiles.{name}.exit.profit_target.value",
        minimum=0.01,
    )
    if not isinstance(exit_config.get("technical_rules"), list):
        raise StrategyProfileError(
            f"profiles.{name}.exit.technical_rules must be a list"
        )
    for key in ("preferred_profit_zone", "break_even", "trailing"):
        if not isinstance(exit_config.get(key), dict) or not isinstance(
            exit_config[key].get("enabled"), bool
        ):
            raise StrategyProfileError(
                f"profiles.{name}.exit.{key} must be an object with enabled"
            )


def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    """Validate and return a deep copy of the canonical strategy document."""
    if not isinstance(document, dict):
        raise StrategyProfileError("strategy profile document must be an object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise StrategyProfileError(f"schema_version must equal {SCHEMA_VERSION}")
    if document.get("paper_trading_only") is not True:
        raise StrategyProfileError("paper_trading_only must remain true")
    profiles = document.get("profiles")
    if not isinstance(profiles, dict):
        raise StrategyProfileError("profiles must be an object")
    expected = set(PROFILE_IDENTITIES)
    actual = set(profiles)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise StrategyProfileError(
            f"profile set mismatch; missing={missing}; extra={extra}"
        )

    for name, identity in PROFILE_IDENTITIES.items():
        profile = profiles[name]
        if not isinstance(profile, dict):
            raise StrategyProfileError(f"profiles.{name} must be an object")
        _nonempty_string(profile.get("version"), f"profiles.{name}.version")
        if not isinstance(profile.get("enabled"), bool):
            raise StrategyProfileError(f"profiles.{name}.enabled must be boolean")
        observed = (
            _nonempty_string(
                profile.get("play_type"), f"profiles.{name}.play_type"
            ).upper(),
            _nonempty_string(
                profile.get("direction"), f"profiles.{name}.direction"
            ).lower(),
            _nonempty_string(
                profile.get("structure"), f"profiles.{name}.structure"
            ).lower(),
        )
        if observed != identity:
            raise StrategyProfileError(
                f"profiles.{name} identity {observed} does not match {identity}"
            )
        regimes = profile.get("market_regime")
        if not isinstance(regimes, dict):
            raise StrategyProfileError(
                f"profiles.{name}.market_regime must be an object"
            )
        _string_list(
            regimes.get("allowed"), f"profiles.{name}.market_regime.allowed"
        )
        _string_list(
            regimes.get("blocked"), f"profiles.{name}.market_regime.blocked"
        )
        _validate_contract_filters(name, profile)
        _validate_entry(name, profile)
        _validate_management(name, profile)
        _validate_exit(name, profile)
        learning = profile.get("learning")
        if not isinstance(learning, dict):
            raise StrategyProfileError(f"profiles.{name}.learning must be an object")
        _number(
            learning.get("minimum_sample_size"),
            f"profiles.{name}.learning.minimum_sample_size",
            minimum=1,
        )
        if learning.get("automatic_application_allowed") is not False:
            raise StrategyProfileError(
                f"profiles.{name} may not automatically apply learning changes"
            )

    return copy.deepcopy(document)


def load_document(path: Path | str = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    source = Path(path)
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StrategyProfileError(f"cannot read strategy profiles: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise StrategyProfileError(
            f"strategy profiles are not valid JSON: {exc}"
        ) from exc
    return validate_document(document)


def load_runtime_state(
    path: Path | str = DEFAULT_RUNTIME_STATE_PATH,
) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {"schema_version": 1, "profiles": {}}
    try:
        state = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "profiles": {}}
    return (
        state
        if isinstance(state, dict)
        else {"schema_version": 1, "profiles": {}}
    )


def effective_profile(
    name: str, document: dict[str, Any] | None = None
) -> dict[str, Any]:
    document = validate_document(document) if document is not None else load_document()
    if name not in PROFILE_IDENTITIES:
        raise StrategyProfileError(f"unknown strategy profile: {name}")
    profile = copy.deepcopy(document["profiles"][name])
    profile["name"] = name
    profile["configuration_hash"] = configuration_hash(
        document["profiles"][name]
    )
    return profile


def profile_for_trade(play_type: str, direction: str) -> str:
    key = (str(play_type or "").upper(), str(direction or "").lower())
    lookup = {
        ("REGULAR", "call"): "regular-call",
        ("REGULAR", "put"): "regular-put",
        ("SWING", "call"): "swing-call",
        ("SWING", "put"): "swing-put",
        ("SPREAD", "put"): "bull-put-spread",
        ("SPREAD", "call"): "bear-call-spread",
    }
    if key not in lookup:
        raise StrategyProfileError(
            f"unsupported trade identity: {key[0]} {key[1]}"
        )
    return lookup[key]


def _consumer_ack(
    runtime_profile: dict[str, Any], consumer: str
) -> tuple[str, str, str]:
    payload = runtime_profile.get(consumer)
    if not isinstance(payload, dict):
        return "", "", ""
    return (
        str(payload.get("version") or ""),
        str(payload.get("configuration_hash") or ""),
        str(payload.get("acknowledged_at") or ""),
    )


def registry_snapshot(
    document: dict[str, Any] | None = None,
    runtime_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return stored and runtime proof without changing any live component."""
    document = validate_document(document) if document is not None else load_document()
    runtime_state = (
        runtime_state
        if isinstance(runtime_state, dict)
        else load_runtime_state()
    )
    runtime_profiles = (
        runtime_state.get("profiles")
        if isinstance(runtime_state.get("profiles"), dict)
        else {}
    )
    snapshots: list[dict[str, Any]] = []
    for name in PROFILE_IDENTITIES:
        profile = document["profiles"][name]
        stored_hash = configuration_hash(profile)
        runtime_profile = (
            runtime_profiles.get(name)
            if isinstance(runtime_profiles.get(name), dict)
            else {}
        )
        scanner_version, scanner_hash, scanner_at = _consumer_ack(
            runtime_profile, "scanner"
        )
        manager_version, manager_hash, manager_at = _consumer_ack(
            runtime_profile, "position_manager"
        )
        has_both = bool(scanner_hash and manager_hash)
        runtime_match = bool(
            has_both
            and scanner_hash == stored_hash
            and manager_hash == stored_hash
            and scanner_version == profile["version"]
            and manager_version == profile["version"]
        )
        if runtime_match:
            status = "ACTIVE"
        elif has_both:
            status = "RUNTIME MISMATCH"
        else:
            status = "FOUNDATION ONLY"
        snapshots.append(
            {
                "name": name,
                "version": profile["version"],
                "enabled": profile["enabled"],
                "play_type": profile["play_type"],
                "direction": profile["direction"],
                "structure": profile["structure"],
                "configuration_hash": stored_hash,
                "runtime_status": status,
                "runtime_match": runtime_match,
                "scanner_loaded_version": scanner_version,
                "scanner_loaded_hash": scanner_hash,
                "scanner_acknowledged_at": scanner_at,
                "position_manager_loaded_version": manager_version,
                "position_manager_loaded_hash": manager_hash,
                "position_manager_acknowledged_at": manager_at,
                "profile": copy.deepcopy(profile),
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "paper_trading_only": True,
        "profiles": snapshots,
    }


def flattened_settings(profile: dict[str, Any]) -> dict[str, Any]:
    """Flatten profile settings into future Discord-editable dot paths."""
    output: dict[str, Any] = {}

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key in sorted(value):
                walk(f"{prefix}.{key}" if prefix else key, value[key])
        elif isinstance(value, list):
            output[prefix] = copy.deepcopy(value)
        else:
            output[prefix] = value

    walk("", profile)
    return output


def current_behavior_audit(
    document: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Machine-readable audit used by documentation and read-only cards."""
    document = validate_document(document) if document is not None else load_document()
    audit = []
    for name in PROFILE_IDENTITIES:
        profile = document["profiles"][name]
        audit.append(
            {
                "profile": name,
                "version": profile["version"],
                "configuration_hash": configuration_hash(profile),
                "entry_model": "regime gate + liquidity + contract/risk filters",
                "management_model": "quote polling with MFE/MAE tracking",
                "exit_model": profile["exit"],
                "dynamic_profit_protection": profile["management"][
                    "dynamic_profit_protection_enabled"
                ],
                "technical_exit": profile["management"][
                    "technical_exit_enabled"
                ],
                "runtime_behavior_changed_by_foundation": False,
            }
        )
    return audit
