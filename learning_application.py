"""Apply Learning Center concepts to live, read-only ticker observations.

This module powers natural-language educational walkthroughs such as:
- "Apply RSI and support/resistance to $F"
- "Use the option-chain lesson on SPY puts"
- "Walk me through volatility on AAPL"

It never adds the symbol to the scanner, changes filters, or places orders.
Observations are separated from interpretations and every explanation cites the
same Learning Center sections used by `/ask` and `/explain`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

import spy_scanner
import learning_center_content as learning
import local_information_engine as info_engine


APPLICATION_WORDS = (
    "apply",
    "analyze",
    "analyse",
    "walk me through",
    "show me",
    "use this on",
    "use that on",
    "use the logic",
    "example with",
    "example on",
    "look at",
    "break down",
    "breakdown",
    "teach me using",
    "how does this look on",
    "how would this work on",
)

# These market and education terms are commonly capitalized but are not tickers.
NON_TICKER_TOKENS = {
    "AM", "PM", "US", "USA", "USD", "ETF", "ETFS", "SEC", "FINRA", "OCC",
    "IRS", "GDP", "CPI", "PCE", "FOMC", "FED", "RSI", "MACD", "ATR", "ADX",
    "VWAP", "SMA", "EMA", "IV", "DTE", "OI", "ITM", "ATM", "OTM", "EPS",
    "EBIT", "EBITDA", "DCF", "FCF", "ROE", "ROIC", "PDT", "GTC", "IOC",
    "API", "APIS", "AI", "PE", "EV", "TTM", "YOY", "QOQ", "IPO", "ADR",
    "REIT", "NAV", "AUM", "MAE", "MFE", "TRIN", "TICK", "PPO", "ROC",
}

COMPANY_ALIASES = {
    "ford": "F",
    "ford motor": "F",
    "apple": "AAPL",
    "microsoft": "MSFT",
    "tesla": "TSLA",
    "nvidia": "NVDA",
    "amazon": "AMZN",
    "alphabet": "GOOGL",
    "google": "GOOGL",
    "meta": "META",
    "facebook": "META",
    "netflix": "NFLX",
    "amd": "AMD",
    "intel": "INTC",
    "disney": "DIS",
    "boeing": "BA",
    "coca cola": "KO",
    "walmart": "WMT",
    "jpmorgan": "JPM",
    "spy": "SPY",
    "s and p 500": "SPY",
    "s&p 500": "SPY",
    "qqq": "QQQ",
    "nasdaq 100": "QQQ",
    "iwm": "IWM",
    "russell 2000": "IWM",
    "dia": "DIA",
    "dow": "DIA",
}

OPTION_TERMS = {
    "option", "options", "call", "calls", "put", "puts", "delta", "gamma",
    "theta", "vega", "rho", "iv", "implied volatility", "option chain",
    "spread", "credit spread", "debit spread", "dte", "open interest",
    "assignment", "exercise", "expiration", "strike", "premium", "greeks",
}
FUNDAMENTAL_TERMS = {
    "fundamental", "fundamentals", "income statement", "balance sheet",
    "cash flow", "revenue", "earnings quality", "valuation", "p e", "pe ratio",
    "debt", "margin", "business model", "moat", "free cash flow", "financials",
}
EVENT_TERMS = {
    "earnings", "news", "event", "catalyst", "dividend", "split", "merger",
    "filing", "sec", "guidance", "corporate action",
}


@dataclass(frozen=True)
class ApplicationRequest:
    ticker: str
    question: str
    explicit_ticker: bool
    option_side: str | None


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def is_application_request(question: str) -> bool:
    normalized = _normalized(question)
    return any(phrase in normalized for phrase in APPLICATION_WORDS)


def _candidate_symbols(question: str) -> list[tuple[str, bool]]:
    candidates: list[tuple[str, bool]] = []
    seen: set[str] = set()

    def add(value: str, explicit: bool) -> None:
        symbol = re.sub(r"[^A-Za-z]", "", value).upper()
        if not 1 <= len(symbol) <= 5 or symbol in NON_TICKER_TOKENS or symbol in seen:
            return
        seen.add(symbol)
        candidates.append((symbol, explicit))

    for match in re.finditer(r"\$([A-Za-z]{1,5})\b", question):
        add(match.group(1), True)
    for match in re.finditer(
        r"\b(?:ticker|symbol)\s*[:=]?\s*([A-Za-z]{1,5})\b",
        question,
        flags=re.IGNORECASE,
    ):
        add(match.group(1), True)

    lowered = question.casefold()
    for name, symbol in sorted(COMPANY_ALIASES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            add(symbol, True)

    for token in re.findall(r"\b[A-Z]{1,5}\b", question):
        add(token, True)
    return candidates


def _verify_symbol(symbol: str) -> bool:
    try:
        quote = spy_scanner.get_quote(symbol) or {}
    except Exception:
        return False
    return spy_scanner.as_float(quote.get("last")) is not None


def parse_application_request(question: str) -> ApplicationRequest | None:
    if not is_application_request(question):
        return None
    for symbol, explicit in _candidate_symbols(question):
        if _verify_symbol(symbol):
            lowered = _normalized(question)
            side = "put" if re.search(r"\bputs?\b", lowered) else None
            if re.search(r"\bcalls?\b", lowered):
                side = "call"
            return ApplicationRequest(symbol, question.strip(), explicit, side)
    return None


def _number(value: Any, digits: int = 2, suffix: str = "") -> str:
    number = spy_scanner.as_float(value)
    if number is None:
        return "unavailable"
    return f"{number:.{digits}f}{suffix}"


def _money(value: Any) -> str:
    number = spy_scanner.as_float(value)
    return f"${number:.2f}" if number is not None else "unavailable"


def _pct(value: Any, digits: int = 1) -> str:
    number = spy_scanner.as_float(value)
    return f"{number:.{digits}f}%" if number is not None else "unavailable"


def _distance_pct(price: float | None, level: float | None) -> float | None:
    if price is None or level is None or price == 0:
        return None
    return (level / price - 1) * 100


def _price_context(snapshot: dict[str, Any]) -> list[str]:
    price = spy_scanner.as_float(snapshot.get("price"))
    sma20 = spy_scanner.as_float(snapshot.get("sma20"))
    sma50 = spy_scanner.as_float(snapshot.get("sma50"))
    sma200 = spy_scanner.as_float(snapshot.get("sma200"))
    rsi = spy_scanner.as_float(snapshot.get("rsi14"))
    macd = spy_scanner.as_float(snapshot.get("macd"))
    atr = spy_scanner.as_float(snapshot.get("atr14"))
    support = spy_scanner.as_float(snapshot.get("support20"))
    resistance = spy_scanner.as_float(snapshot.get("resistance20"))
    vwap = spy_scanner.as_float(snapshot.get("intraday_vwap"))
    relative_volume = spy_scanner.as_float(snapshot.get("relative_volume"))

    observations = [
        (
            f"Price **{_money(price)}** · day change **{_pct(snapshot.get('change_pct'))}** · "
            f"recorded regime **{snapshot.get('regime') or 'unavailable'}**"
        ),
        (
            f"SMA20 **{_money(sma20)}** · SMA50 **{_money(sma50)}** · "
            f"SMA200 **{_money(sma200)}**"
        ),
        (
            f"RSI14 **{_number(rsi, 1)}** · MACD **{_number(macd, 3)}** · "
            f"ATR14 **{_money(atr)}**"
        ),
        (
            f"20-day support **{_money(support)}** ({_pct(_distance_pct(price, support))} from price) · "
            f"resistance **{_money(resistance)}** ({_pct(_distance_pct(price, resistance))} from price)"
        ),
        (
            f"Intraday VWAP **{_money(vwap)}** · relative volume **{_number(relative_volume, 2)}x** · "
            f"bid/ask spread **{_pct((spy_scanner.as_float(snapshot.get('spread_pct')) or 0) * 100, 2)}**"
        ),
    ]
    return observations


def _technical_interpretation(snapshot: dict[str, Any]) -> list[str]:
    price = spy_scanner.as_float(snapshot.get("price"))
    sma20 = spy_scanner.as_float(snapshot.get("sma20"))
    sma50 = spy_scanner.as_float(snapshot.get("sma50"))
    sma200 = spy_scanner.as_float(snapshot.get("sma200"))
    rsi = spy_scanner.as_float(snapshot.get("rsi14"))
    macd = spy_scanner.as_float(snapshot.get("macd"))
    atr = spy_scanner.as_float(snapshot.get("atr14"))
    support = spy_scanner.as_float(snapshot.get("support20"))
    resistance = spy_scanner.as_float(snapshot.get("resistance20"))
    relative_volume = spy_scanner.as_float(snapshot.get("relative_volume"))
    vwap = spy_scanner.as_float(snapshot.get("intraday_vwap"))
    notes: list[str] = []

    if price is not None and sma20 is not None and sma50 is not None:
        if price > sma20 > sma50:
            notes.append("Price is above rising-reference averages in bullish order; that supports trend context but is not an entry by itself.")
        elif price < sma20 < sma50:
            notes.append("Price is below the short and intermediate averages in bearish order; rallies may still occur, so invalidation remains necessary.")
        else:
            notes.append("Price and moving averages are mixed, which is evidence of transition or range rather than clean directional alignment.")
    if price is not None and sma200 is not None:
        notes.append(
            f"Price is **{'above' if price >= sma200 else 'below'}** the 200-day average, a long-horizon context measure rather than a timing signal."
        )
    if rsi is not None:
        if rsi >= 70:
            notes.append("RSI is above 70: momentum is strong or stretched, but 'overbought' does not guarantee reversal.")
        elif rsi <= 30:
            notes.append("RSI is below 30: selling momentum is strong or stretched, but 'oversold' does not guarantee a bounce.")
        elif rsi >= 55:
            notes.append("RSI is in a moderately positive momentum zone without being an automatic buy signal.")
        elif rsi <= 45:
            notes.append("RSI is in a moderately negative momentum zone without being an automatic sell signal.")
        else:
            notes.append("RSI is near the middle of its range, so it offers limited directional confirmation by itself.")
    if macd is not None:
        notes.append(
            f"The simplified MACD value is **{'positive' if macd > 0 else 'negative' if macd < 0 else 'near zero'}**; slope and signal-line history would be needed for a complete MACD reading."
        )
    if price and atr is not None:
        notes.append(
            f"ATR is about **{atr / price * 100:.1f}% of price**, a recent movement estimate useful for judging whether stops and targets are unrealistically tight."
        )
    if price is not None and support is not None and resistance is not None:
        room_up = (resistance / price - 1) * 100
        room_down = (support / price - 1) * 100
        notes.append(
            f"The observed 20-day range leaves roughly **{room_up:+.1f}%** to resistance and **{room_down:+.1f}%** to support; these are zones, not guaranteed barriers."
        )
    if price is not None and vwap is not None:
        notes.append(
            f"Price is **{'above' if price >= vwap else 'below'} intraday VWAP**, describing current-session positioning rather than future certainty."
        )
    if relative_volume is not None:
        if relative_volume >= 1.5:
            notes.append("Relative volume is elevated, so the move has stronger-than-normal participation for the current comparison method.")
        elif relative_volume < 0.75:
            notes.append("Relative volume is light, making breakouts and displayed moves less convincing unless a catalyst explains the timing.")
        else:
            notes.append("Relative volume is near ordinary levels and does not add strong participation evidence.")
    return notes


def _option_rows(ticker: str, side: str | None) -> tuple[list[str], list[str]]:
    sides = [side] if side else ["call", "put"]
    observations: list[str] = []
    interpretation: list[str] = []
    for option_side in sides:
        if not option_side:
            continue
        try:
            ranked = info_engine.ranked_option_chain(
                side=option_side, limit=3, symbol=ticker
            )
        except Exception as exc:
            observations.append(f"{option_side.title()} chain unavailable: {type(exc).__name__}.")
            continue
        if not ranked:
            observations.append(f"No usable {option_side} contracts were returned for the configured expiration range.")
            continue
        observations.append(f"**Highest-ranked {option_side}s for study**")
        for item in ranked:
            width_pct = spy_scanner.as_float(item.get("width_pct"))
            iv = spy_scanner.as_float(item.get("iv"))
            observations.append(
                "• `{}' · exp {} · strike {} · bid/ask {}/{} · Δ {} · θ {} · IV {} · OI {:,} · vol {:,} · width {} · {}".format(
                    item.get("symbol") or "unknown",
                    item.get("expiration") or "unknown",
                    _money(item.get("strike")),
                    _money(item.get("bid")),
                    _money(item.get("ask")),
                    _number(item.get("delta"), 2),
                    _number(item.get("theta"), 3),
                    _pct(iv * 100 if iv is not None else None, 1),
                    int(item.get("open_interest") or 0),
                    int(item.get("volume") or 0),
                    _pct(width_pct * 100 if width_pct is not None else None, 1),
                    "liquidity PASS" if item.get("liquidity_pass") else "liquidity FAIL",
                ).replace("`'", "`")
            )
        best = ranked[0]
        interpretation.append(
            f"The first {option_side} is ranked for relative liquidity quality, not predicted profit. Compare its delta, DTE, IV, width, and maximum loss with the lesson before considering a structure."
        )
        if not best.get("liquidity_pass"):
            interpretation.append(
                f"Even the highest-ranked {option_side} failed configured liquidity rules, so the educational conclusion is to study the chain rather than force a paper entry."
            )
    return observations, interpretation


def _fundamental_limitations(question: str) -> list[str]:
    normalized = _normalized(question)
    if not any(term in normalized for term in FUNDAMENTAL_TERMS):
        return []
    return [
        "The local runtime currently tracks quotes, price history, technical context, options chains, news links, and trade outcomes. It does **not** maintain complete income statements, balance sheets, cash-flow statements, consensus forecasts, or valuation models for every ticker.",
        "A proper fundamental application would require current filings, segment data, share count, debt maturities, margins, cash conversion, and valuation assumptions. TradeBot will identify those missing inputs instead of pretending a moving average is a balance sheet.",
    ]


def _event_context(ticker: str, question: str) -> list[str]:
    normalized = _normalized(question)
    if not any(term in normalized for term in EVENT_TERMS):
        return []
    try:
        items = info_engine.fetch_ticker_news(ticker)
    except Exception:
        items = []
    if not items:
        return [
            "No current cached headlines were available. Confirm earnings, dividends, filings, and scheduled events from primary sources before applying an event lesson."
        ]
    lines = ["Recent cached headlines for source verification:"]
    for item in items[:4]:
        title = str(item.get("title") or "Untitled")[:180]
        lines.append(f"• {title}")
    lines.append("Headlines are prompts for research, not trade signals; open the original source and verify its timestamp and status.")
    return lines


def _references(question: str) -> list[str]:
    matches = learning.search_library(question, limit=5)
    references: list[str] = []
    for _, section in matches:
        reference = f"{learning.channel_reference(section.channel)} → **{section.heading}**"
        if reference not in references:
            references.append(reference)
        if len(references) >= 4:
            break
    return references


def apply_to_ticker(request: ApplicationRequest) -> str:
    snapshot = info_engine.market_snapshot(request.ticker)
    normalized = _normalized(request.question)
    option_requested = any(term in normalized for term in OPTION_TERMS)

    lines = [
        f"# Educational application · {request.ticker}",
        "This uses current read-only data to demonstrate the requested lesson. It does not add the ticker to the scanner or recommend a trade.",
        "",
        "## What the system can observe",
        *[f"• {item}" for item in _price_context(snapshot)],
        "",
        "## Applying the lesson",
        *[f"• {item}" for item in _technical_interpretation(snapshot)],
    ]

    if option_requested:
        option_observations, option_interpretation = _option_rows(
            request.ticker, request.option_side
        )
        lines.extend(
            [
                "",
                "## Option-chain application",
                *[f"• {item}" for item in option_observations],
                *[f"• {item}" for item in option_interpretation],
            ]
        )

    limitations = _fundamental_limitations(request.question)
    event_context = _event_context(request.ticker, request.question)
    if limitations or event_context:
        lines.extend(
            [
                "",
                "## Missing or separate evidence",
                *[f"• {item}" for item in limitations],
                *[f"• {item}" for item in event_context],
            ]
        )

    references = _references(request.question)
    if references:
        lines.extend(
            [
                "",
                "## Learning Center references",
                *[f"• {item}" for item in references],
            ]
        )

    lines.extend(
        [
            "",
            "## Questions a learner should answer",
            "• Which observations support the thesis and which oppose it?",
            "• What exact price, time, volatility, or event condition would invalidate the idea?",
            "• Is the expected movement large enough relative to ATR, nearby levels, option cost, spread, and time decay?",
            "",
            f"_Data observed {snapshot.get('observed_at') or 'at request time'}. Educational walkthrough only, not financial advice._",
        ]
    )
    return "\n".join(lines)[:3900]


def answer(question: str) -> str:
    request = parse_application_request(question)
    if not request:
        if is_application_request(question):
            return (
                "# Ticker needed for a live application\nUse an explicit symbol such as "
                "`$F`, `$AAPL`, or `ticker:SPY`. TradeBot will verify the symbol, "
                "use available read-only quote, chart, technical, chain, and news "
                "data, and cite the lesson sections. It will not add the ticker to "
                "the scanner or invent unavailable fundamentals."
            )
        return learning.answer(question)
    try:
        return apply_to_ticker(request)
    except Exception as exc:
        return (
            f"# Educational application unavailable\nTradeBot verified **{request.ticker}** "
            f"but could not complete the current data walkthrough: "
            f"`{type(exc).__name__}: {str(exc)[:180]}`\n\n"
            "The static lesson remains available through `/explain`, and no scanner "
            "state or brokerage action was changed."
        )[:3900]


def validate_parser(
    verifier: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    original = globals()["_verify_symbol"]
    if verifier is not None:
        globals()["_verify_symbol"] = verifier
    try:
        probes = {
            "Apply RSI and support to $F": "F",
            "Walk me through gamma risk on SPY calls": "SPY",
            "Show me option-chain liquidity on ticker:AAPL": "AAPL",
            "Use the valuation lesson on Ford": "F",
        }
        failures: list[str] = []
        for query, expected in probes.items():
            parsed = parse_application_request(query)
            actual = parsed.ticker if parsed else "none"
            if actual != expected:
                failures.append(f"{query!r}: expected {expected}, got {actual}")
        if failures:
            raise RuntimeError("Application parser validation failed: " + "; ".join(failures))
        return {"probes": len(probes)}
    finally:
        globals()["_verify_symbol"] = original


if __name__ == "__main__":
    result = validate_parser(lambda symbol: bool(symbol))
    print(f"Validated {result['probes']} educational application requests.")
