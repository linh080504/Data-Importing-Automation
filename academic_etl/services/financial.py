"""Financial format standardization service.

Handles parsing, formatting, and currency conversion for the canonical format:
    CURRENCY AMOUNT_LOW-AMOUNT_HIGH ($USD_LOW-USD_HIGH)

Examples:
    "INR 5k-15k ($60-180)"
    "VND 20m-40m ($800-1600)"
    "$5,000-$15,000"
    "INR 150k-300k ($1800-3600)"
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.utils import timezone

from .country_registry import get_country_config, get_currency, get_denomination_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class FinancialData:
    currency: str = ""
    amount_low: Decimal | None = None
    amount_high: Decimal | None = None
    usd_low: Decimal | None = None
    usd_high: Decimal | None = None
    raw: str = ""
    formatted: str = ""
    period: str = ""  # annual | semester | total | monthly


# ---------------------------------------------------------------------------
# Currency symbol -> ISO 4217 mapping
# ---------------------------------------------------------------------------

_SYMBOL_TO_CURRENCY = {
    "$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR",
    "₫": "VND", "₩": "KRW", "₱": "PHP", "฿": "THB", "₪": "ILS",
    "R$": "BRL", "RM": "MYR", "Rp": "IDR", "₦": "NGN", "R": "ZAR",
    "zł": "PLN", "kr": "SEK",
}

_CURRENCY_NAME_MAP = {
    "rs": "INR", "rs.": "INR", "inr": "INR", "rupee": "INR", "rupees": "INR",
    "usd": "USD", "dollar": "USD", "dollars": "USD",
    "eur": "EUR", "euro": "EUR", "euros": "EUR",
    "gbp": "GBP", "pound": "GBP", "pounds": "GBP",
    "jpy": "JPY", "yen": "JPY", "円": "JPY",
    "cny": "CNY", "rmb": "CNY", "yuan": "CNY",
    "vnd": "VND", "đồng": "VND", "dong": "VND",
    "krw": "KRW", "won": "KRW", "원": "KRW",
    "thb": "THB", "baht": "THB",
    "myr": "MYR", "ringgit": "MYR",
    "idr": "IDR", "rupiah": "IDR",
    "php": "PHP", "peso": "PHP",
    "sgd": "SGD",
    "aud": "AUD", "cad": "CAD",
    "brl": "BRL", "real": "BRL",
    "mxn": "MXN",
    "egp": "EGP",
    "sar": "SAR", "riyal": "SAR",
    "aed": "AED", "dirham": "AED",
    "ngn": "NGN", "naira": "NGN",
    "kes": "KES",
    "zar": "ZAR", "rand": "ZAR",
    "try": "TRY", "lira": "TRY",
    "rub": "RUB", "ruble": "RUB",
    "pkr": "PKR",
    "bdt": "BDT", "taka": "BDT",
}


# ---------------------------------------------------------------------------
# Exchange rate management
# ---------------------------------------------------------------------------

def fetch_exchange_rates(currencies: list[str] | None = None) -> dict[str, Decimal]:
    """Fetch current exchange rates from frankfurter.app (free, no key needed).

    Returns dict: {currency_code: rate} where rate = how many units of currency per 1 USD.
    Results are cached in the ExchangeRate model.
    """
    from academic_etl.models import ExchangeRate

    cache_hours = getattr(settings, "ETL_EXCHANGE_RATE_CACHE_HOURS", 24)
    cutoff = timezone.now() - timezone.timedelta(hours=cache_hours)

    # Check if we have fresh rates
    latest = ExchangeRate.objects.filter(fetched_at__gte=cutoff).first()
    if latest:
        cached = {}
        for rate in ExchangeRate.objects.filter(fetched_at__gte=cutoff):
            cached[rate.currency_code] = rate.rate_to_usd
        if currencies is None or all(c in cached for c in currencies):
            return cached

    # Fetch fresh rates
    api_url = getattr(settings, "ETL_EXCHANGE_RATE_API", "https://api.frankfurter.app/latest")
    try:
        resp = requests.get(api_url, params={"from": "USD"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        rates = {}
        now = timezone.now()
        for code, rate in data.get("rates", {}).items():
            dec_rate = Decimal(str(rate))
            rates[code] = dec_rate
            ExchangeRate.objects.create(
                currency_code=code,
                rate_to_usd=dec_rate,
                source="frankfurter",
            )
        logger.info("Fetched %d exchange rates from frankfurter.app", len(rates))
        return rates
    except Exception as exc:
        logger.warning("Failed to fetch exchange rates: %s — using cached rates", exc)
        # Fallback to any cached rates (even stale)
        cached = {}
        for rate in ExchangeRate.objects.order_by("currency_code", "-fetched_at").distinct("currency_code"):
            cached[rate.currency_code] = rate.rate_to_usd
        if not cached:
            # Use SQLite-compatible fallback (distinct on not supported)
            seen = set()
            for rate in ExchangeRate.objects.order_by("-fetched_at"):
                if rate.currency_code not in seen:
                    cached[rate.currency_code] = rate.rate_to_usd
                    seen.add(rate.currency_code)
        return cached


def _get_cached_rates() -> dict[str, Decimal]:
    """Get the most recent rate for each currency from DB."""
    from academic_etl.models import ExchangeRate
    rates = {}
    seen = set()
    for rate in ExchangeRate.objects.order_by("-fetched_at"):
        if rate.currency_code not in seen:
            rates[rate.currency_code] = rate.rate_to_usd
            seen.add(rate.currency_code)
    return rates


def convert_to_usd(amount: Decimal, currency_code: str) -> Decimal | None:
    """Convert an amount in local currency to USD."""
    if not amount or not currency_code:
        return None
    code = currency_code.upper()
    if code == "USD":
        return amount
    rates = _get_cached_rates()
    rate = rates.get(code)
    if rate is None:
        rates = fetch_exchange_rates([code])
        rate = rates.get(code)
    if rate and rate > 0:
        return (amount / rate).quantize(Decimal("0.01"))
    return None


# ---------------------------------------------------------------------------
# Parse financial strings
# ---------------------------------------------------------------------------

_AMOUNT_RE = re.compile(
    r"(?P<number>\d[\d,]*\.?\d*)\s*(?P<denom>[a-zA-Z万丈тыс]*)",
)

CANONICAL_FINANCIAL_RE = re.compile(
    r"^(?P<currency>[A-Z]{3})\s+"
    r"(?P<low>\d+(?:\.\d+)?)(?P<low_unit>[km]?)"
    r"(?:-(?P<high>\d+(?:\.\d+)?)(?P<high_unit>[km]?))?"
    r"\s+\(\$(?P<usd_low>\d+(?:\.\d+)?)"
    r"(?:-(?P<usd_high>\d+(?:\.\d+)?))?\)$"
)
_USD_EQ_RE = re.compile(
    r"\(\s*(?:USD|\$)\s*(?P<low>\d[\d,]*(?:\.\d+)?)"
    r"(?:\s*[-â€“â€”]\s*(?P<high>\d[\d,]*(?:\.\d+)?))?\s*\)",
    re.IGNORECASE,
)


def _detect_currency(text: str, country_code: str = "") -> str:
    """Detect the currency from a financial string."""
    probe = _USD_EQ_RE.sub("", text)
    # Check for currency names/codes
    lower = probe.lower()
    for name, code in _CURRENCY_NAME_MAP.items():
        if re.search(r"\b" + re.escape(name) + r"\b", lower):
            return code
    # Check for explicit symbols after code/name detection. Some symbols such
    # as "R" are plain letters and would otherwise match inside "INR".
    for symbol, code in _SYMBOL_TO_CURRENCY.items():
        if symbol in probe:
            return code
    # Fall back to country default
    if country_code:
        return get_currency(country_code)
    return "USD"


def _parse_amount(text: str, denom_config: dict) -> Decimal | None:
    """Parse a single amount value with denomination support."""
    text = text.strip().replace(",", "")
    match = _AMOUNT_RE.match(text)
    if not match:
        return None
    try:
        number = Decimal(match.group("number"))
    except (InvalidOperation, ValueError):
        return None
    denom = match.group("denom").strip()
    if denom:
        multiplier = denom_config.get(denom)
        if multiplier is None:
            # Case-insensitive lookup
            for key, val in denom_config.items():
                if key.lower() == denom.lower():
                    multiplier = val
                    break
        if multiplier:
            number *= Decimal(str(multiplier))
    return number


def _parse_plain_decimal(text: str | None) -> Decimal | None:
    if text is None:
        return None
    try:
        return Decimal(str(text).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def parse_financial_string(text: str, country_code: str = "") -> FinancialData:
    """Parse a financial string into structured FinancialData.

    Handles formats like:
        "INR 5k-15k ($60-180)"
        "VND 20tr-40tr"
        "$5,000-$15,000"
        "INR 1.5L"
        "3万-5万円"
        "15 triệu - 40 triệu VND"
    """
    if not text or not text.strip():
        return FinancialData(raw=text or "")

    raw = text.strip()
    currency = _detect_currency(raw, country_code)
    denom_config = get_denomination_config(country_code)

    # Merge global denomination defaults
    base_denoms = {"k": 1_000, "K": 1_000, "M": 1_000_000}
    merged_denoms = {**base_denoms, **denom_config}

    usd_match = _USD_EQ_RE.search(raw)
    parsed_usd_low = _parse_plain_decimal(usd_match.group("low")) if usd_match else None
    parsed_usd_high = _parse_plain_decimal(usd_match.group("high")) if usd_match else None

    # Remove the USD equivalent part if present: "($240-600)" or "(USD 240-600)"
    cleaned = re.sub(r"\(\s*\$[\d,.\s\-–—to]+\)", "", raw)
    cleaned = re.sub(r"\(\s*USD[\d,.\s\-–—to]+\)", "", cleaned, flags=re.IGNORECASE)

    for name in sorted(_CURRENCY_NAME_MAP.keys(), key=len, reverse=True):
        cleaned = re.sub(r"\b" + re.escape(name) + r"\b", " ", cleaned, flags=re.IGNORECASE)
    # Remove currency symbols for amount parsing. Letter symbols like "R" must
    # match as standalone tokens so they do not alter codes such as INR.
    for symbol in _SYMBOL_TO_CURRENCY:
        if symbol.isalpha():
            cleaned = re.sub(r"\b" + re.escape(symbol) + r"\b", " ", cleaned)
        else:
            cleaned = cleaned.replace(symbol, " ")

    # Split on range separators
    parts = re.split(r"\s*[-–—]\s*|\s+to\s+", cleaned.strip())
    parts = [p.strip() for p in parts if p.strip()]

    amounts: list[Decimal] = []
    for part in parts:
        amt = _parse_amount(part, merged_denoms)
        if amt is not None:
            amounts.append(amt)

    if not amounts:
        return FinancialData(raw=raw, currency=currency)

    amount_low = min(amounts)
    amount_high = max(amounts) if len(amounts) > 1 else None

    # Detect period
    period = ""
    lower = raw.lower()
    if "month" in lower or "tháng" in lower:
        period = "monthly"
    elif "semester" in lower or "học kỳ" in lower:
        period = "semester"
    elif "year" in lower or "annual" in lower or "năm" in lower or "p.a" in lower:
        period = "annual"
    elif "total" in lower or "toàn khóa" in lower:
        period = "total"
    else:
        period = "annual"  # default assumption

    # Prefer a sourced USD equivalent already present in the input. Fall back to
    # exchange-rate conversion only when the input did not provide USD values.
    usd_low = parsed_usd_low if parsed_usd_low is not None else convert_to_usd(amount_low, currency)
    usd_high = (
        parsed_usd_high
        if parsed_usd_high is not None
        else convert_to_usd(amount_high, currency) if amount_high else None
    )

    result = FinancialData(
        currency=currency,
        amount_low=amount_low,
        amount_high=amount_high,
        usd_low=usd_low,
        usd_high=usd_high,
        raw=raw,
        period=period,
    )
    result.formatted = format_financial(result, country_code)
    return result


# ---------------------------------------------------------------------------
# Format financial data
# ---------------------------------------------------------------------------

def _best_denomination(amount: Decimal, denom_config: dict) -> tuple[str, Decimal]:
    """Choose the most readable denomination for a value."""
    if not denom_config:
        return _auto_denomination(amount)

    # Sort denominations by multiplier descending
    sorted_denoms = sorted(denom_config.items(), key=lambda x: x[1], reverse=True)

    for abbrev, multiplier in sorted_denoms:
        if multiplier <= 0:
            continue
        divided = amount / Decimal(str(multiplier))
        # Use this denomination if the result is >= 1 and looks clean
        if divided >= 1:
            return abbrev, divided

    return "", amount


def _auto_denomination(amount: Decimal) -> tuple[str, Decimal]:
    """Fallback denomination for unknown countries."""
    if amount >= 1_000_000:
        return "m", amount / Decimal("1000000")
    if amount >= 1_000:
        return "k", amount / Decimal("1000")
    return "", amount


def _format_number(val: Decimal) -> str:
    """Format a number removing trailing zeros."""
    if val == int(val):
        return str(int(val))
    # Show at most 1 decimal
    rounded = val.quantize(Decimal("0.1"))
    if rounded == int(rounded):
        return str(int(rounded))
    return str(rounded)


def format_financial(data: FinancialData, country_code: str = "") -> str:
    """Format FinancialData into the canonical display string.

    Output: "CURRENCY AMOUNT_LOW-AMOUNT_HIGH ($USD_LOW-USD_HIGH)"
    """
    if data.amount_low is None:
        return data.raw or ""

    currency = data.currency or "USD"

    # The import CSV contract uses global compact units: k for thousands and m
    # for millions. Local units such as L, crore, tr, or jt are parsed as input
    # but are not emitted in the final field.
    denom_low, val_low = _auto_denomination(data.amount_low)
    formatted_low = _format_number(val_low)

    if data.amount_high and data.amount_high != data.amount_low:
        denom_high, val_high = _auto_denomination(data.amount_high)
        # Use same denomination if possible for consistency
        if denom_low == denom_high:
            local_part = f"{currency} {formatted_low}{denom_low}-{_format_number(val_high)}{denom_high}"
        else:
            local_part = f"{currency} {formatted_low}{denom_low}-{_format_number(val_high)}{denom_high}"
    else:
        local_part = f"{currency} {formatted_low}{denom_low}"

    # Add USD equivalent
    if data.usd_low is not None and currency != "USD":
        usd_low_str = _format_number(data.usd_low)
        if data.usd_high is not None and data.usd_high != data.usd_low:
            usd_high_str = _format_number(data.usd_high)
            return f"{local_part} (${usd_low_str}-{usd_high_str})"
        return f"{local_part} (${usd_low_str})"

    return local_part


def is_canonical_financials(value: str, country_code: str = "", require_usd: bool = True) -> bool:
    """Return True when value matches the CSV import contract for financials."""
    text = " ".join(str(value or "").split())
    match = CANONICAL_FINANCIAL_RE.fullmatch(text)
    if not match:
        return False
    expected = get_currency(country_code) if country_code else ""
    if expected and match.group("currency").upper() != expected:
        return False

    low = _parse_plain_decimal(match.group("low"))
    high = _parse_plain_decimal(match.group("high")) or low
    usd_low = _parse_plain_decimal(match.group("usd_low"))
    usd_high = _parse_plain_decimal(match.group("usd_high")) or usd_low
    if low is None or high is None or usd_low is None or usd_high is None:
        return False
    if low <= 0 or high < low or usd_low <= 0 or usd_high < usd_low:
        return False
    if require_usd and usd_low is None:
        return False
    return True


# ---------------------------------------------------------------------------
# End-to-end convenience
# ---------------------------------------------------------------------------

def standardize_financials(raw: str, currency_code: str = "", country_code: str = "") -> dict:
    """Parse, convert, and format a financial string in one call.

    Returns a dict ready to update model fields:
        {raw, formatted, currency, amount_low, amount_high, usd_low, usd_high, period}
    """
    if not raw or not raw.strip():
        return {}

    # If currency not provided, try to detect from country
    if not currency_code and country_code:
        currency_code = get_currency(country_code)

    data = parse_financial_string(raw, country_code)

    return {
        "raw": data.raw,
        "formatted": data.formatted,
        "currency": data.currency,
        "amount_low": data.amount_low,
        "amount_high": data.amount_high,
        "usd_low": data.usd_low,
        "usd_high": data.usd_high,
        "period": data.period,
    }
