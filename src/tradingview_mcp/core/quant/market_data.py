"""
Market data layer.

**Why this works on a free TradingView plan.** The system never calls a
TradingView data API. TradingView is used only to observe *what you are looking
at* — the symbol and the chart interval — which any logged-in browser session
exposes regardless of plan tier. All OHLCV comes from free public endpoints
(Yahoo Finance, Binance, Stooq). Nothing here requires a TradingView
subscription, an API key, or scraping paid data.

Providers are tried in order and the first that returns a usable frame wins, so
a single endpoint being rate-limited or geo-blocked degrades rather than breaks.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

_UA = "tradingview-mcp/1.0 (+market-data)"
_TIMEOUT = 15

# ── interval vocabulary ───────────────────────────────────────────────────────
# One canonical set; every provider maps into it. The previous implementation
# collapsed every intraday interval to "1h", so a 1-minute chart was silently
# analysed on hourly bars. Intervals are now first-class.

CANONICAL_INTERVALS = ("1m", "2m", "5m", "15m", "30m", "1h", "2h", "4h", "1d", "1wk", "1mo")

# Seconds per bar — drives bar-close-aligned polling in the monitor.
INTERVAL_SECONDS = {
    "1m": 60, "2m": 120, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "1d": 86400,
    "1wk": 604800, "1mo": 2592000,
}

# How far back each interval can realistically be fetched from free sources.
MAX_LOOKBACK = {
    "1m": "7d", "2m": "60d", "5m": "60d", "15m": "60d", "30m": "60d",
    "1h": "730d", "2h": "730d", "4h": "730d",
    "1d": "10y", "1wk": "10y", "1mo": "max",
}

# TradingView writes intervals as bare minute counts ("1", "15", "240") or
# letter-suffixed ("1D", "1W"). Normalise both forms.
_TV_INTERVAL_MAP = {
    "1": "1m", "2": "2m", "3": "5m", "5": "5m", "10": "15m", "15": "15m",
    "30": "30m", "45": "30m", "60": "1h", "120": "2h", "180": "4h", "240": "4h",
    "1d": "1d", "d": "1d", "1w": "1wk", "w": "1wk", "1m": "1mo", "m": "1mo",
    "1mo": "1mo", "1h": "1h", "4h": "4h", "5m": "5m", "15m": "15m", "30m": "30m",
}


def normalize_interval(raw: Optional[str]) -> str:
    """
    Map any interval spelling to the canonical set.

    TradingView is ambiguous: "1M" means one month on its chart toolbar while
    "1m" conventionally means one minute. The toolbar uses uppercase for
    day/week/month, so case is the disambiguator and must be preserved.
    """
    if not raw:
        return "1d"
    s = str(raw).strip()
    if s in ("1M", "M"):
        return "1mo"
    if s in ("1W", "W"):
        return "1wk"
    if s in ("1D", "D"):
        return "1d"
    low = s.lower()
    if low in CANONICAL_INTERVALS:
        return low
    if low in _TV_INTERVAL_MAP:
        return _TV_INTERVAL_MAP[low]
    digits = re.fullmatch(r"(\d+)", low)
    if digits:
        mins = int(digits.group(1))
        for cand, secs in sorted(INTERVAL_SECONDS.items(), key=lambda kv: kv[1]):
            if secs >= mins * 60:
                return cand
    return "1d"


def interval_seconds(interval: str) -> int:
    return INTERVAL_SECONDS.get(normalize_interval(interval), 86400)


def seconds_to_next_close(interval: str, now: Optional[float] = None) -> float:
    """Seconds until the current bar closes — used to align polling to bar close."""
    secs = interval_seconds(interval)
    t = time.time() if now is None else now
    if secs >= 86400:  # daily and slower: don't try to align to a session close
        return float(secs)
    return float(secs - (t % secs))


# ── symbol translation ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SymbolSpec:
    """A TradingView symbol resolved into per-provider identifiers."""
    raw: str
    exchange: str = ""
    ticker: str = ""
    asset_class: str = "equity"     # equity | crypto | forex | index | futures
    yahoo: str = ""
    binance: str = ""
    stooq: str = ""

    def to_dict(self) -> dict:
        return {"raw": self.raw, "exchange": self.exchange, "ticker": self.ticker,
                "asset_class": self.asset_class, "yahoo": self.yahoo,
                "binance": self.binance, "stooq": self.stooq}


_CRYPTO_EXCHANGES = {
    "BINANCE", "COINBASE", "KRAKEN", "BYBIT", "OKX", "KUCOIN", "BITSTAMP",
    "BITFINEX", "GATEIO", "MEXC", "HUOBI", "CRYPTO", "BITGET", "BITMEX",
    "DERIBIT", "UPBIT", "BITHUMB", "POLONIEX", "PHEMEX", "WOONETWORK",
    # TradingView pseudo-exchanges that carry crypto symbols.
    "CRYPTOCAP", "INDEX", "COINBASEPRO", "BINANCEUS", "CRYPTOCOM",
}
_QUOTE_ASSETS = ("USDT", "USDC", "BUSD", "TUSD", "FDUSD", "USD", "EUR", "GBP", "BTC", "ETH")

# Major coins that TradingView often shows as a bare ticker with no quote asset —
# CRYPTOCAP:DOGE, INDEX:BTC, CRYPTOCAP:TOTAL. Without this, "DOGE" was resolved as
# an equity and every provider returned nothing.
_BARE_CRYPTO = {
    "BTC", "ETH", "XRP", "SOL", "DOGE", "ADA", "AVAX", "DOT", "LINK", "MATIC",
    "LTC", "BCH", "TRX", "SHIB", "UNI", "ATOM", "XLM", "ETC", "FIL", "APT",
    "ARB", "OP", "NEAR", "ICP", "INJ", "SUI", "SEI", "TIA", "RNDR", "IMX",
    "AAVE", "MKR", "SAND", "MANA", "AXS", "GRT", "ALGO", "VET", "HBAR", "PEPE",
    "BNB", "TON", "USDT", "USDC", "XMR", "EOS", "FTM", "RUNE", "CRV", "LDO",
}

# TradingView aggregate symbols that have no tradeable instrument behind them.
_CRYPTOCAP_AGGREGATES = {"TOTAL", "TOTAL2", "TOTAL3", "TOTALDEFI", "OTHERS",
                         "BTC.D", "USDT.D", "STABLE.C"}

# TVC and other index pseudo-exchanges → the Yahoo ticker for the same series.
_TVC_MAP = {
    "DXY": "DX-Y.NYB", "GOLD": "GC=F", "SILVER": "SI=F", "USOIL": "CL=F",
    "UKOIL": "BZ=F", "NATGAS": "NG=F", "COPPER": "HG=F", "VIX": "^VIX",
    "US10Y": "^TNX", "US02Y": "^IRX", "US30Y": "^TYX", "SPX": "^GSPC",
    "NDX": "^NDX", "DJI": "^DJI", "RUT": "^RUT", "NI225": "^N225",
    "DAX": "^GDAXI", "UKX": "^FTSE", "HSI": "^HSI", "SX5E": "^STOXX50E",
    "NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK", "SENSEX": "^BSESN",
}
_INDEX_EXCHANGES = {"TVC", "SP", "DJ", "CBOE", "CME_MINI", "ECONOMICS", "FRED"}

# Indices whose provider ticker cannot be derived mechanically.
_INDEX_MAP = {
    "NIFTY": "^NSEI", "NIFTY50": "^NSEI", "CNXNIFTY": "^NSEI",
    "BANKNIFTY": "^NSEBANK", "NIFTYBANK": "^NSEBANK",
    "SENSEX": "^BSESN", "SPX": "^GSPC", "SPX500": "^GSPC", "US500": "^GSPC",
    "NDX": "^NDX", "US100": "^NDX", "DJI": "^DJI", "US30": "^DJI",
    "VIX": "^VIX", "RUT": "^RUT", "FTSE": "^FTSE", "DAX": "^GDAXI",
    "NIKKEI": "^N225", "NI225": "^N225", "HSI": "^HSI", "KOSPI": "^KS11",
}

# Exchange suffixes Yahoo appends for non-US listings.
_EXCHANGE_SUFFIX = {
    "NSE": ".NS", "BSE": ".BO", "LSE": ".L", "TSX": ".TO", "TSXV": ".V",
    "ASX": ".AX", "HKEX": ".HK", "SSE": ".SS", "SZSE": ".SZ", "TSE": ".T",
    "BIST": ".IS", "EGX": ".CA", "KLSE": ".KL", "MYX": ".KL", "SGX": ".SI",
    "FWB": ".F", "XETR": ".DE", "EURONEXT": ".PA", "BME": ".MC", "MIL": ".MI",
    "OMX": ".ST", "SWB": ".SW",
}


def parse_symbol(raw: str, exchange_hint: str = "") -> SymbolSpec:
    """
    Resolve a TradingView-style symbol into provider identifiers.

    Handles ``BINANCE:BTCUSDT``, ``NSE:RELIANCE``, bare ``AAPL``, index aliases
    and forex pairs. Unknown formats fall through to the raw ticker, which is
    correct for US equities.
    """
    s = (raw or "").strip().upper()
    exchange = (exchange_hint or "").strip().upper()

    if ":" in s:
        left, right = s.split(":", 1)
        exchange, s = left.strip(), right.strip()

    s = re.sub(r"[^A-Z0-9._^-]", "", s)
    if not s:
        return SymbolSpec(raw=raw or "", exchange=exchange)

    # ── TradingView pseudo-exchanges ──
    # CRYPTOCAP aggregates (TOTAL, BTC.D) have no tradeable instrument behind them.
    if exchange == "CRYPTOCAP" and s in _CRYPTOCAP_AGGREGATES:
        return SymbolSpec(raw=raw, exchange=exchange, ticker=s, asset_class="aggregate")

    # TVC / SP / DJ / CBOE carry index and commodity series under their own tickers.
    if exchange in _INDEX_EXCHANGES:
        mapped = _TVC_MAP.get(s)
        if mapped:
            return SymbolSpec(raw=raw, exchange=exchange, ticker=s,
                              asset_class="index", yahoo=mapped)

    # Index aliases — neither equities nor crypto.
    base = s.replace(".", "").replace("-", "")
    if base in _INDEX_MAP:
        return SymbolSpec(raw=raw, exchange=exchange, ticker=s, asset_class="index",
                          yahoo=_INDEX_MAP[base])
    if base in _TVC_MAP:
        return SymbolSpec(raw=raw, exchange=exchange, ticker=s, asset_class="index",
                          yahoo=_TVC_MAP[base])

    # Bare crypto ticker with no quote asset (CRYPTOCAP:DOGE, INDEX:BTC, or plain DOGE).
    # Priced against USD, which is the tradeable proxy for the series being charted.
    if base in _BARE_CRYPTO and not any(
            base.endswith(q) and len(base) > len(q) for q in _QUOTE_ASSETS):
        return SymbolSpec(raw=raw, exchange=exchange, ticker=s, asset_class="crypto",
                          yahoo=f"{base}-USD", binance=f"{base}USDT")

    # Forex is checked before crypto: a pair like EURUSD ends in "USD" and would
    # otherwise be misread as a crypto pair with base "EUR".
    _FIAT = ("USD", "EUR", "JPY", "GBP", "CHF", "AUD", "CAD", "NZD")
    if exchange in ("FX", "FOREX", "OANDA", "FX_IDC", "FXCM", "SAXO") or (
            not exchange and len(s) == 6 and s.isalpha()
            and s[:3] in _FIAT and s[3:] in _FIAT):
        return SymbolSpec(raw=raw, exchange=exchange, ticker=s, asset_class="forex",
                          yahoo=f"{s}=X")

    is_crypto = exchange in _CRYPTO_EXCHANGES or any(
        s.endswith(q) and len(s) > len(q) + 1 for q in _QUOTE_ASSETS)

    if is_crypto:
        quote = next((q for q in _QUOTE_ASSETS if s.endswith(q) and len(s) > len(q)), "USDT")
        coin = s[: -len(quote)] or s
        stable = ("USDT", "USDC", "BUSD", "TUSD", "FDUSD", "USD")
        yahoo_quote = "USD" if quote in stable else quote
        # Binance quotes against USDT, not USD — a raw ...USD pair does not exist there.
        binance_quote = "USDT" if quote in stable else quote
        return SymbolSpec(raw=raw, exchange=exchange, ticker=s, asset_class="crypto",
                          yahoo=f"{coin}-{yahoo_quote}", binance=f"{coin}{binance_quote}")

    suffix = _EXCHANGE_SUFFIX.get(exchange, "")
    return SymbolSpec(raw=raw, exchange=exchange, ticker=s, asset_class="equity",
                      yahoo=f"{s}{suffix}", stooq=f"{s}.US" if not suffix else s)


# ── HTTP with graceful degradation ────────────────────────────────────────────

def _http_json(url: str, timeout: int = _TIMEOUT) -> Optional[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        pass
    # Optional proxy path, if the project's proxy manager is configured.
    try:
        from tradingview_mcp.core.services.proxy_manager import build_opener_with_proxy
        opener = build_opener_with_proxy(_UA)
        with opener.open(url, timeout=timeout + 5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _http_text(url: str, timeout: int = _TIMEOUT) -> Optional[str]:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


# ── providers ─────────────────────────────────────────────────────────────────

_YF_INTERVAL = {"1m": "1m", "2m": "2m", "5m": "5m", "15m": "15m", "30m": "30m",
                "1h": "60m", "2h": "60m", "4h": "60m", "1d": "1d", "1wk": "1wk", "1mo": "1mo"}
_BINANCE_INTERVAL = {"1m": "1m", "2m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
                     "1h": "1h", "2h": "2h", "4h": "4h", "1d": "1d", "1wk": "1w", "1mo": "1M"}


def _fetch_yahoo(spec: SymbolSpec, interval: str, lookback: str) -> Optional[pd.DataFrame]:
    sym = spec.yahoo or spec.ticker
    if not sym:
        return None
    yf_int = _YF_INTERVAL.get(interval, "1d")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
           f"?interval={yf_int}&range={lookback}&includePrePost=false")
    data = _http_json(url)
    try:
        result = data["chart"]["result"][0]
        ts = result["timestamp"]
        q = result["indicators"]["quote"][0]
    except (TypeError, KeyError, IndexError):
        return None

    df = pd.DataFrame({
        "date": pd.to_datetime(ts, unit="s", utc=True),
        "open": q.get("open"), "high": q.get("high"),
        "low": q.get("low"), "close": q.get("close"), "volume": q.get("volume"),
    }).dropna(subset=["close"])
    if df.empty:
        return None
    df = df.set_index("date")
    # Yahoo has no native 2h/4h; resample from its 60m bars.
    if interval in ("2h", "4h"):
        df = _resample(df, interval)
    return df


def _fetch_binance(spec: SymbolSpec, interval: str, lookback: str) -> Optional[pd.DataFrame]:
    if spec.asset_class != "crypto" or not spec.binance:
        return None
    b_int = _BINANCE_INTERVAL.get(interval, "1d")
    url = (f"https://api.binance.com/api/v3/klines?symbol={spec.binance}"
           f"&interval={b_int}&limit=1000")
    data = _http_json(url)
    if not isinstance(data, list) or not data:
        return None
    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "trades", "taker_base", "taker_quote", "ignore"])
    df = df[["open_time", "open", "high", "low", "close", "volume"]].astype(
        {"open": float, "high": float, "low": float, "close": float, "volume": float})
    df["date"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df.drop(columns=["open_time"]).set_index("date")


def _fetch_stooq(spec: SymbolSpec, interval: str, lookback: str) -> Optional[pd.DataFrame]:
    """Stooq only serves end-of-day data — a daily/weekly/monthly fallback."""
    if interval not in ("1d", "1wk", "1mo") or not spec.stooq:
        return None
    period = {"1d": "d", "1wk": "w", "1mo": "m"}[interval]
    url = f"https://stooq.com/q/d/l/?s={spec.stooq.lower()}&i={period}"
    text = _http_text(url)
    if not text or "Date" not in text.split("\n", 1)[0]:
        return None
    from io import StringIO
    df = pd.read_csv(StringIO(text))
    df.columns = [c.strip().lower() for c in df.columns]
    if "close" not in df.columns:
        return None
    df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
    return df.dropna(subset=["date", "close"]).set_index("date")


def _resample(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    rule = {"2h": "2h", "4h": "4h", "1d": "1D", "1wk": "1W"}.get(interval)
    if not rule:
        return df
    out = df.resample(rule).agg({"open": "first", "high": "max", "low": "min",
                                 "close": "last", "volume": "sum"})
    return out.dropna(subset=["close"])


_PROVIDERS = (("binance", _fetch_binance), ("yahoo", _fetch_yahoo), ("stooq", _fetch_stooq))


# ── cache ─────────────────────────────────────────────────────────────────────

@dataclass
class _CacheEntry:
    df: pd.DataFrame
    fetched_at: float
    provider: str


_CACHE: dict[tuple, _CacheEntry] = {}


def _cache_ttl(interval: str) -> float:
    """Cache for a fraction of a bar so repeated scans do not re-hit the network."""
    return max(15.0, interval_seconds(interval) * 0.2)


@dataclass
class MarketData:
    """Fetched OHLCV plus the provenance needed to report it honestly."""
    df: pd.DataFrame
    symbol: SymbolSpec
    interval: str
    provider: str
    fetched_at: datetime
    from_cache: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def bars(self) -> int:
        return len(self.df)

    @property
    def last_bar_time(self):
        return self.df.index[-1] if len(self.df) else None

    def to_dict(self) -> dict:
        return {"symbol": self.symbol.to_dict(), "interval": self.interval,
                "provider": self.provider, "bars": self.bars,
                "fetched_at": self.fetched_at.isoformat(),
                "last_bar": self.last_bar_time.isoformat() if self.last_bar_time is not None else None,
                "from_cache": self.from_cache, "warnings": self.warnings}


def fetch_ohlcv(
    symbol: str,
    interval: str = "1d",
    exchange: str = "",
    lookback: Optional[str] = None,
    use_cache: bool = True,
    providers: Optional[tuple[str, ...]] = None,
) -> MarketData:
    """
    Fetch OHLCV for a symbol at an interval, trying providers in order.

    Raises RuntimeError only when every provider fails — a single provider being
    unreachable is a warning, not an error.
    """
    interval = normalize_interval(interval)
    spec = parse_symbol(symbol, exchange)
    lookback = lookback or MAX_LOOKBACK.get(interval, "1y")
    key = (spec.raw, spec.exchange, interval, lookback)

    if use_cache and key in _CACHE:
        hit = _CACHE[key]
        if time.time() - hit.fetched_at < _cache_ttl(interval):
            return MarketData(hit.df, spec, interval, hit.provider,
                              datetime.fromtimestamp(hit.fetched_at, tz=timezone.utc), True)

    warnings: list[str] = []
    wanted = providers or tuple(name for name, _ in _PROVIDERS)
    for name, fn in _PROVIDERS:
        if name not in wanted:
            continue
        try:
            df = fn(spec, interval, lookback)
        except Exception as exc:
            warnings.append(f"{name}: {type(exc).__name__}: {exc}")
            continue
        if df is not None and len(df) >= 2:
            df = df[~df.index.duplicated(keep="last")].sort_index()
            _CACHE[key] = _CacheEntry(df, time.time(), name)
            return MarketData(df, spec, interval, name, datetime.now(timezone.utc), False, warnings)
        warnings.append(f"{name}: no usable data for {spec.yahoo or spec.ticker} @ {interval}")

    # Stale cache beats no data: a slightly old frame is more useful than a crash.
    if key in _CACHE:
        hit = _CACHE[key]
        warnings.append("all providers failed; serving stale cached data")
        return MarketData(hit.df, spec, interval, hit.provider + " (stale)",
                          datetime.fromtimestamp(hit.fetched_at, tz=timezone.utc), True, warnings)

    raise RuntimeError(
        f"No provider returned data for {symbol!r} at interval {interval!r}. "
        f"Attempts: {'; '.join(warnings) or 'none'}"
    )


def clear_cache() -> None:
    _CACHE.clear()


def synthetic_ohlcv(bars: int = 600, seed: int = 0, start_price: float = 100.0,
                    interval: str = "1d") -> pd.DataFrame:
    """
    Deterministic synthetic series for tests and offline demos.

    Explicitly labelled synthetic. It exists so the UI can be exercised without a
    network connection — never as a silent fallback for real market data.
    """
    import numpy as np
    rng = np.random.default_rng(seed)
    freq = {"1m": "min", "5m": "5min", "15m": "15min", "1h": "h", "1d": "D"}.get(interval, "D")
    idx = pd.date_range(end=pd.Timestamp.now(tz="UTC").floor("min"), periods=bars, freq=freq)
    ret = rng.normal(0.0003, 0.012, bars)
    px = start_price * np.exp(np.cumsum(ret))
    return pd.DataFrame({
        "open": px * (1 + rng.normal(0, 0.002, bars)),
        "high": px * (1 + np.abs(rng.normal(0, 0.006, bars))),
        "low": px * (1 - np.abs(rng.normal(0, 0.006, bars))),
        "close": px,
        "volume": rng.lognormal(11, 0.5, bars),
    }, index=idx)
