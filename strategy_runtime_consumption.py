"""Load canonical strategy profiles into the existing scanner and position manager.

This is the compatibility runtime for strategy-platform PR 2.  It deliberately
keeps the current scanner algorithms and exit model, but replaces their shared
configuration constants at each decision boundary with the matching profile's
validated values.  The adapters record durable version/hash acknowledgements so
Discord and GitHub may distinguish stored configuration from configuration that
the running process actually loaded.

No updater, process supervisor, brokerage write, or service restart is involved.
"""

from __future__ import annotations

import copy
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

import ford_scan
import strategy_profiles

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
ACTIVE_CONFIG_PATH = STATE_DIR / "strategy-active.json"
LAST_VALID_CONFIG_PATH = STATE_DIR / "strategy-last-valid.json"
RUNTIME_STATE_PATH = strategy_profiles.DEFAULT_RUNTIME_STATE_PATH
TRADE_PLAN_DIR = STATE_DIR / "strategy-trade-plans"
RUNTIME_SCHEMA_VERSION = 2
ADAPTER_VERSION = "strategy-runtime-compat-v1"

STRATEGY_ROW_FIELDS = (
    "strategy_profile",
    "strategy_version",
    "strategy_configuration_hash",
    "strategy_snapshot_status",
)

_BASE_LOAD_DOCUMENT = strategy_profiles.load_document
_STATE_LOCK = threading.RLock()
_ADAPTER_LOCK = threading.RLock()
_INSTALLED_MODULES: dict[int, dict[str, Callable[..., Any]]] = {}
_CACHED_DOCUMENT: dict[str, Any] | None = None
_LAST_LOAD_META: dict[str, Any] = {}


class StrategyRuntimeError(RuntimeError):
    """Raised when a valid profile cannot be represented by this runtime stage."""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return copy.deepcopy(default)
    return payload if isinstance(payload, dict) else copy.deepcopy(default)


def _value(profile: dict[str, Any], path: str) -> Any:
    current: Any = profile
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise StrategyRuntimeError(
                f"profile {profile.get('name', 'unknown')} is missing {path}"
            )
        current = current[part]
    return current


def _profile_from_document(document: dict[str, Any], name: str) -> dict[str, Any]:
    profile = copy.deepcopy(document["profiles"][name])
    profile["name"] = name
    profile["configuration_hash"] = strategy_profiles.configuration_hash(
        document["profiles"][name]
    )
    return profile


def _same(document: dict[str, Any], names: tuple[str, ...], path: str) -> Any:
    values = [_value(_profile_from_document(document, name), path) for name in names]
    first = values[0]
    if any(value != first for value in values[1:]):
        raise StrategyRuntimeError(
            f"PR 2 compatibility adapter requires matching {path} for "
            + ", ".join(names)
        )
    return first


def validate_adapter_document(document: dict[str, Any]) -> dict[str, Any]:
    """Reject profile features that PR 2 does not yet claim to execute."""
    document = strategy_profiles.validate_document(document)

    regular = ("regular-call", "regular-put")
    swing = (
        "swing-call",
        "swing-put",
        "bull-put-spread",
        "bear-call-spread",
    )
    for path in ("contract_filters.dte_min", "contract_filters.dte_max"):
        _same(document, regular, path)
        _same(document, swing, path)
    if float(_same(document, regular, "contract_filters.dte_max")) >= float(
        _same(document, swing, "contract_filters.dte_min")
    ):
        raise StrategyRuntimeError(
            "regular and swing DTE ranges must not overlap in the PR 2 adapter"
        )
    _same(document, tuple(strategy_profiles.PROFILE_IDENTITIES), "contract_filters.strike_band_pct")

    expected_regimes = {
        "regular-call": {"BULLISH / CONTROLLED"},
        "regular-put": {"BEARISH / CONTROLLED"},
        "swing-call": {"BULLISH / CONTROLLED"},
        "swing-put": {"BEARISH / CONTROLLED"},
        "bull-put-spread": {"BULLISH / CONTROLLED", "NEUTRAL / RANGE"},
        "bear-call-spread": {"BEARISH / CONTROLLED", "NEUTRAL / RANGE"},
    }
    expected_regime_parameters = {
        "daily_sma_fast_period": 20,
        "daily_sma_slow_period": 50,
        "daily_rsi_period": 14,
        "intraday_momentum_fast_bars": 5,
        "intraday_momentum_slow_bars": 20,
        "uses_vwap": True,
        "uses_recent_slope": True,
    }

    for name in strategy_profiles.PROFILE_IDENTITIES:
        profile = _profile_from_document(document, name)
        allowed = set(profile["market_regime"]["allowed"])
        if allowed != expected_regimes[name]:
            raise StrategyRuntimeError(
                f"{name} allowed regimes require the later configurable rule engine"
            )
        if profile["entry"].get("minimum_setup_score") is not None:
            raise StrategyRuntimeError(
                f"{name} minimum setup score requires the later ranking-control phase"
            )
        regime_rule = next(
            (
                rule
                for rule in profile["entry"]["rules"]
                if rule.get("id") == "market-regime"
            ),
            None,
        )
        if not regime_rule or regime_rule.get("parameters") != expected_regime_parameters:
            raise StrategyRuntimeError(
                f"{name} technical regime parameters require the later rule engine"
            )
        management = profile["management"]
        unsupported_management = (
            "dynamic_profit_protection_enabled",
            "technical_exit_enabled",
            "momentum_exit_enabled",
            "thesis_invalidation_enforced",
        )
        if any(bool(management.get(key)) for key in unsupported_management):
            raise StrategyRuntimeError(
                f"{name} enables management logic reserved for the dynamic-exit phase"
            )
        exit_config = profile["exit"]
        if exit_config.get("technical_rules"):
            raise StrategyRuntimeError(
                f"{name} technical exit rules require the dynamic-exit phase"
            )
        for key in ("preferred_profit_zone", "break_even", "trailing"):
            if bool((exit_config.get(key) or {}).get("enabled")):
                raise StrategyRuntimeError(
                    f"{name} {key} requires the dynamic-exit phase"
                )

    return document


def _initialize_active_config() -> None:
    if ACTIVE_CONFIG_PATH.exists():
        return
    defaults = validate_adapter_document(_BASE_LOAD_DOCUMENT())
    _atomic_json(ACTIVE_CONFIG_PATH, defaults)


def load_active_document() -> dict[str, Any]:
    """Load the active file, falling back atomically to the last valid document."""
    global _CACHED_DOCUMENT, _LAST_LOAD_META
    with _STATE_LOCK:
        _initialize_active_config()
        attempted_error = ""
        source = "active"
        try:
            document = validate_adapter_document(
                _BASE_LOAD_DOCUMENT(ACTIVE_CONFIG_PATH)
            )
        except (strategy_profiles.StrategyProfileError, StrategyRuntimeError) as exc:
            attempted_error = f"{type(exc).__name__}: {exc}"
            source = "last-valid-fallback"
            if _CACHED_DOCUMENT is not None:
                document = copy.deepcopy(_CACHED_DOCUMENT)
            elif LAST_VALID_CONFIG_PATH.exists():
                document = validate_adapter_document(
                    _BASE_LOAD_DOCUMENT(LAST_VALID_CONFIG_PATH)
                )
            else:
                document = validate_adapter_document(_BASE_LOAD_DOCUMENT())
        _CACHED_DOCUMENT = copy.deepcopy(document)
        _atomic_json(LAST_VALID_CONFIG_PATH, document)
        _LAST_LOAD_META = {
            "loaded_at": now_iso(),
            "source": source,
            "active_path": str(ACTIVE_CONFIG_PATH),
            "last_valid_path": str(LAST_VALID_CONFIG_PATH),
            "fallback_used": source != "active",
            "error": attempted_error,
            "adapter_version": ADAPTER_VERSION,
        }
        return copy.deepcopy(document)


def last_load_metadata() -> dict[str, Any]:
    with _STATE_LOCK:
        return copy.deepcopy(_LAST_LOAD_META)


def _runtime_state() -> dict[str, Any]:
    return _read_json(
        RUNTIME_STATE_PATH,
        {"schema_version": RUNTIME_SCHEMA_VERSION, "profiles": {}},
    )


def acknowledge_profiles(
    document: dict[str, Any],
    consumer: str,
    names: tuple[str, ...] | list[str] | None = None,
    *,
    detail: str = "",
) -> dict[str, Any]:
    if consumer not in {"scanner", "position_manager"}:
        raise StrategyRuntimeError(f"unsupported runtime consumer: {consumer}")
    selected = tuple(names or strategy_profiles.PROFILE_IDENTITIES)
    timestamp = now_iso()
    with _STATE_LOCK:
        state = _runtime_state()
        state["schema_version"] = RUNTIME_SCHEMA_VERSION
        state["adapter_version"] = ADAPTER_VERSION
        state["updated_at"] = timestamp
        state["configuration_load"] = last_load_metadata()
        profiles = state.setdefault("profiles", {})
        for name in selected:
            profile = document["profiles"][name]
            runtime_profile = profiles.setdefault(name, {})
            runtime_profile[consumer] = {
                "version": str(profile["version"]),
                "configuration_hash": strategy_profiles.configuration_hash(profile),
                "acknowledged_at": timestamp,
                "adapter_version": ADAPTER_VERSION,
                "process_id": os.getpid(),
                "detail": detail or "validated profile loaded by compatibility adapter",
            }
        _atomic_json(RUNTIME_STATE_PATH, state)
        return copy.deepcopy(state)


def _profile_name(play_type: Any, direction: Any) -> str:
    return strategy_profiles.profile_for_trade(str(play_type), str(direction))


def _profile_for_trade(
    document: dict[str, Any], play_type: Any, direction: Any
) -> dict[str, Any]:
    return _profile_from_document(document, _profile_name(play_type, direction))


def _scanner_globals(profile: dict[str, Any]) -> dict[str, Any]:
    filters = profile["contract_filters"]
    values = {
        "MIN_OPEN_INTEREST": int(filters["min_open_interest"]),
        "MIN_OPTION_VOLUME": int(filters["min_option_volume"]),
        "MAX_BID_ASK_PCT": float(filters["max_bid_ask_pct"]),
        "MAX_RISK_PER_TRADE": float(filters["max_position_risk_dollars"]),
    }
    if profile["structure"] == "long-option":
        values.update(
            {
                "SINGLE_LEG_DELTA_MIN": float(filters["delta_min"]),
                "SINGLE_LEG_DELTA_MAX": float(filters["delta_max"]),
                "MAX_CONTRACT_ASK": float(filters["max_contract_ask"]),
            }
        )
    else:
        values.update(
            {
                "SPREAD_SHORT_DELTA_MIN": float(filters["short_delta_min"]),
                "SPREAD_SHORT_DELTA_MAX": float(filters["short_delta_max"]),
                "MIN_SPREAD_CREDIT": float(filters["min_credit"]),
            }
        )
    return values


def _manager_globals(profile: dict[str, Any]) -> dict[str, Any]:
    exit_config = profile["exit"]
    if profile["structure"] == "long-option":
        return {
            "SINGLE_STOP_PCT": float(exit_config["hard_stop"]["value"]),
            "SINGLE_TAKE_PROFIT_PCT": float(
                exit_config["profit_target"]["value"]
            ),
        }
    return {
        "SPREAD_STOP_MULTIPLE": float(exit_config["hard_stop"]["value"]),
        "SPREAD_TAKE_PROFIT_PCT": float(
            exit_config["profit_target"]["value"]
        ),
        "SPREAD_EXIT_DTE": int(exit_config["expiration"].get("dte", 5)),
    }


@contextmanager
def _temporary_globals(module: Any, values: dict[str, Any]) -> Iterator[None]:
    with _ADAPTER_LOCK:
        previous = {name: getattr(module, name) for name in values}
        for name, value in values.items():
            setattr(module, name, value)
        try:
            yield
        finally:
            for name, value in previous.items():
                setattr(module, name, value)


def _snapshot_path(trade_id: str) -> Path:
    safe = "".join(character for character in trade_id if character.isalnum() or character in "-_.")
    return TRADE_PLAN_DIR / f"{safe or 'unknown'}.json"


def _write_trade_plan(
    row: dict[str, Any], profile: dict[str, Any], snapshot_status: str
) -> dict[str, Any]:
    trade_id = str(row.get("trade_id") or "")
    payload = {
        "trade_id": trade_id,
        "profile": profile["name"],
        "version": profile["version"],
        "configuration_hash": profile["configuration_hash"],
        "snapshot_status": snapshot_status,
        "captured_at": now_iso(),
        "effective_profile": {
            key: copy.deepcopy(value)
            for key, value in profile.items()
            if key not in {"name", "configuration_hash"}
        },
    }
    if trade_id:
        _atomic_json(_snapshot_path(trade_id), payload)
    row["strategy_profile"] = profile["name"]
    row["strategy_version"] = str(profile["version"])
    row["strategy_configuration_hash"] = profile["configuration_hash"]
    row["strategy_snapshot_status"] = snapshot_status
    return payload


def _load_trade_profile(
    row: dict[str, Any], document: dict[str, Any]
) -> dict[str, Any]:
    trade_id = str(row.get("trade_id") or "")
    path = _snapshot_path(trade_id) if trade_id else None
    if path and path.exists():
        payload = _read_json(path, {})
        effective = payload.get("effective_profile")
        name = str(payload.get("profile") or "")
        if isinstance(effective, dict) and name in strategy_profiles.PROFILE_IDENTITIES:
            profile = copy.deepcopy(effective)
            profile["name"] = name
            profile["configuration_hash"] = str(
                payload.get("configuration_hash")
                or strategy_profiles.configuration_hash(effective)
            )
            row["strategy_profile"] = name
            row["strategy_version"] = str(payload.get("version") or profile.get("version") or "")
            row["strategy_configuration_hash"] = profile["configuration_hash"]
            row["strategy_snapshot_status"] = str(
                payload.get("snapshot_status") or "ENTRY-PINNED"
            )
            return profile

    profile = _profile_for_trade(
        document, row.get("play_type"), row.get("call_or_put")
    )
    status = "LEGACY-RUNTIME-ASSIGNED" if trade_id else "RUNTIME-CURRENT"
    _write_trade_plan(row, profile, status)
    return profile


def _ensure_row_fields(module: Any) -> None:
    for field in STRATEGY_ROW_FIELDS:
        if field not in module.LOG_HEADER:
            module.LOG_HEADER.append(field)


def install(module: Any = ford_scan) -> dict[str, Any]:
    """Attach profile adapters once and acknowledge the loaded runtime contract."""
    module_key = id(module)
    with _ADAPTER_LOCK:
        if module_key in _INSTALLED_MODULES:
            document = load_active_document()
            acknowledge_profiles(document, "scanner", detail="adapter already installed")
            acknowledge_profiles(
                document, "position_manager", detail="adapter already installed"
            )
            return health()

        document = load_active_document()
        _ensure_row_fields(module)
        originals: dict[str, Callable[..., Any]] = {
            name: getattr(module, name)
            for name in (
                "pick_expirations",
                "filter_strikes",
                "recently_tracked",
                "scan_single_legs",
                "scan_credit_spreads",
                "candidate_to_row",
                "evaluate_open_row",
            )
        }

        def pick_expirations(expirations, today):
            active = load_active_document()
            values = {
                "REGULAR_MIN_DTE": int(
                    active["profiles"]["regular-call"]["contract_filters"]["dte_min"]
                ),
                "REGULAR_MAX_DTE": int(
                    active["profiles"]["regular-call"]["contract_filters"]["dte_max"]
                ),
                "MIN_DTE": int(
                    active["profiles"]["swing-call"]["contract_filters"]["dte_min"]
                ),
                "MAX_DTE": int(
                    active["profiles"]["swing-call"]["contract_filters"]["dte_max"]
                ),
            }
            with _temporary_globals(module, values):
                return originals["pick_expirations"](expirations, today)

        def filter_strikes(strikes, spot):
            active = load_active_document()
            band = float(
                active["profiles"]["regular-call"]["contract_filters"]["strike_band_pct"]
            )
            with _temporary_globals(module, {"STRIKE_BAND_PCT": band}):
                return originals["filter_strikes"](strikes, spot)

        def recently_tracked(rows, candidate, timestamp):
            active = load_active_document()
            profile = _profile_for_trade(
                active, candidate.get("play_type"), candidate.get("call_or_put")
            )
            cooldown = int(profile["contract_filters"]["reentry_cooldown_minutes"])
            with _temporary_globals(module, {"REENTRY_COOLDOWN_MINUTES": cooldown}):
                return originals["recently_tracked"](rows, candidate, timestamp)

        def scan_single_legs(chain, kind, expiration, play_type, market_context=None):
            active = load_active_document()
            profile = _profile_for_trade(active, play_type, kind)
            if not profile["enabled"]:
                acknowledge_profiles(active, "scanner", [profile["name"]], detail="profile disabled")
                return []
            with _temporary_globals(module, _scanner_globals(profile)):
                candidates = originals["scan_single_legs"](
                    chain, kind, expiration, play_type, market_context
                )
            for candidate in candidates:
                candidate["strategy_profile"] = profile["name"]
                candidate["strategy_version"] = profile["version"]
                candidate["strategy_configuration_hash"] = profile[
                    "configuration_hash"
                ]
            acknowledge_profiles(
                active,
                "scanner",
                [profile["name"]],
                detail="long-option scan executed with profile values",
            )
            return candidates

        def scan_credit_spreads(chain, kind, expiration, market_context=None):
            active = load_active_document()
            profile = _profile_for_trade(active, "SPREAD", kind)
            if not profile["enabled"]:
                acknowledge_profiles(active, "scanner", [profile["name"]], detail="profile disabled")
                return []
            with _temporary_globals(module, _scanner_globals(profile)):
                candidates = originals["scan_credit_spreads"](
                    chain, kind, expiration, market_context
                )
            for candidate in candidates:
                candidate["strategy_profile"] = profile["name"]
                candidate["strategy_version"] = profile["version"]
                candidate["strategy_configuration_hash"] = profile[
                    "configuration_hash"
                ]
            acknowledge_profiles(
                active,
                "scanner",
                [profile["name"]],
                detail="credit-spread scan executed with profile values",
            )
            return candidates

        def candidate_to_row(candidate, rows, timestamp):
            row = originals["candidate_to_row"](candidate, rows, timestamp)
            active = load_active_document()
            profile = _profile_for_trade(
                active, candidate.get("play_type"), candidate.get("call_or_put")
            )
            _write_trade_plan(row, profile, "ENTRY-PINNED")
            return row

        def evaluate_open_row(row, quotes, timestamp):
            active = load_active_document()
            profile = _load_trade_profile(row, active)
            with _temporary_globals(module, _manager_globals(profile)):
                evaluation = originals["evaluate_open_row"](row, quotes, timestamp)
            evaluation["strategy_profile"] = profile["name"]
            evaluation["strategy_version"] = profile["version"]
            evaluation["strategy_configuration_hash"] = profile[
                "configuration_hash"
            ]
            acknowledge_profiles(
                active,
                "position_manager",
                [profile["name"]],
                detail="open position evaluated with pinned profile values",
            )
            return evaluation

        module.pick_expirations = pick_expirations
        module.filter_strikes = filter_strikes
        module.recently_tracked = recently_tracked
        module.scan_single_legs = scan_single_legs
        module.scan_credit_spreads = scan_credit_spreads
        module.candidate_to_row = candidate_to_row
        module.evaluate_open_row = evaluate_open_row
        _INSTALLED_MODULES[module_key] = originals

        acknowledge_profiles(
            document,
            "scanner",
            detail="all current profile adapters validated and loaded",
        )
        acknowledge_profiles(
            document,
            "position_manager",
            detail="all current profile adapters validated and loaded",
        )
        return health()


def health() -> dict[str, Any]:
    document = load_active_document()
    state = _runtime_state()
    snapshot = strategy_profiles.registry_snapshot(document, state)
    return {
        "adapter_version": ADAPTER_VERSION,
        "active_config": str(ACTIVE_CONFIG_PATH),
        "last_valid_config": str(LAST_VALID_CONFIG_PATH),
        "runtime_state": str(RUNTIME_STATE_PATH),
        "trade_plan_directory": str(TRADE_PLAN_DIR),
        "configuration_load": last_load_metadata(),
        "profiles": {
            item["name"]: {
                "version": item["version"],
                "configuration_hash": item["configuration_hash"],
                "runtime_status": item["runtime_status"],
            }
            for item in snapshot["profiles"]
        },
        "paper_trading_only": True,
        "updater_involved": False,
    }
