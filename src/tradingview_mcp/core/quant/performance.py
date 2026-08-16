"""
Full performance analytics, in the shape of TradingView's Strategy Tester.

The backtester in ``backtest.py`` returns headline numbers. This module produces
the complete report: an **All / Long / Short** breakdown, per-trade excursion
(MAE/MFE), drawdown *and* run-up with their durations, streak analysis, a monthly
returns table, and the risk ratios a desk actually reads.

Two deliberate departures from the way most retail testers present results:

* **Long and short are reported separately.** A strategy that is profitable
  overall but loses money on every short is two different strategies wearing one
  name, and the blended row hides that entirely.
* **Ratios that can be misleading say so.** Profit factor on four trades, Sharpe
  on two months of data, and Calmar with no meaningful drawdown are all reported
  with a sample-size caveat rather than a confident number.

Formula sources are named inline; several of these ratios have more than one
definition in circulation and the choice matters.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from .backtest import BacktestResult, Trade

# Below this many trades, ratios computed from trade outcomes are noise.
MIN_TRADES_FOR_CONFIDENCE = 20
# Below this many bars, annualised figures extrapolate too aggressively to trust.
MIN_BARS_FOR_ANNUALISED = 120


def _safe(x: float, default: float = 0.0) -> float:
    return float(x) if isinstance(x, (int, float)) and math.isfinite(x) else default


@dataclass
class SideStats:
    """
    Trade statistics for one side of the book — the All / Long / Short columns
    of TradingView's Performance Summary.
    """
    side: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    percent_profitable: float = 0.0

    net_profit_pct: float = 0.0
    gross_profit_pct: float = 0.0
    gross_loss_pct: float = 0.0
    profit_factor: float = float("nan")

    avg_trade_pct: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    win_loss_ratio: float = float("nan")

    largest_win_pct: float = 0.0
    largest_loss_pct: float = 0.0

    avg_bars: float = 0.0
    avg_bars_winning: float = 0.0
    avg_bars_losing: float = 0.0

    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    avg_mae_pct: float = 0.0        # mean maximum adverse excursion
    avg_mfe_pct: float = 0.0        # mean maximum favourable excursion
    commission_paid_pct: float = 0.0

    @property
    def reliable(self) -> bool:
        return self.total_trades >= MIN_TRADES_FOR_CONFIDENCE

    def to_dict(self) -> dict:
        d = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in self.__dict__.items()}
        d["reliable"] = self.reliable
        return d


@dataclass
class RiskMetrics:
    """Return- and drawdown-based statistics computed from the equity curve."""
    cagr_pct: float = 0.0
    volatility_pct: float = 0.0
    downside_deviation_pct: float = 0.0

    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    omega: float = float("nan")
    ulcer_index: float = 0.0
    martin_ratio: float = float("nan")     # UPI: CAGR / Ulcer Index
    k_ratio: float = float("nan")

    max_drawdown_pct: float = 0.0
    max_drawdown_bars: int = 0
    max_runup_pct: float = 0.0
    max_runup_bars: int = 0
    recovery_factor: float = float("nan")
    time_to_recover_bars: Optional[int] = None

    var_95_pct: float = 0.0
    cvar_95_pct: float = 0.0
    tail_ratio: float = float("nan")
    skew: float = 0.0
    excess_kurtosis: float = 0.0

    best_bar_pct: float = 0.0
    worst_bar_pct: float = 0.0
    positive_bars_pct: float = 0.0
    time_in_market_pct: float = 0.0

    annualised_reliable: bool = True

    def to_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in self.__dict__.items()}


@dataclass
class PerformanceReport:
    strategy: str
    symbol: str
    interval: str
    bars: int
    period_start: str
    period_end: str

    all_trades: SideStats
    long_trades: SideStats
    short_trades: SideStats
    risk: RiskMetrics

    buy_and_hold_pct: float = 0.0
    excess_return_pct: float = 0.0
    initial_capital: float = 0.0
    commission_pct: float = 0.0
    slippage_pct: float = 0.0

    monthly_returns: dict = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=pd.Series, repr=False)

    def to_dict(self, include_curve: bool = False) -> dict:
        out = {
            "strategy": self.strategy, "symbol": self.symbol, "interval": self.interval,
            "bars": self.bars, "period_start": self.period_start,
            "period_end": self.period_end,
            "all": self.all_trades.to_dict(),
            "long": self.long_trades.to_dict(),
            "short": self.short_trades.to_dict(),
            "risk": self.risk.to_dict(),
            "buy_and_hold_pct": round(self.buy_and_hold_pct, 3),
            "excess_return_pct": round(self.excess_return_pct, 3),
            "initial_capital": self.initial_capital,
            "costs": {"commission_pct": self.commission_pct,
                      "slippage_pct": self.slippage_pct},
            "monthly_returns": self.monthly_returns,
            "caveats": self.caveats,
        }
        if include_curve and len(self.equity_curve):
            out["equity_curve"] = [{"t": str(t), "equity": round(float(v), 6)}
                                   for t, v in self.equity_curve.items()]
        return out


# ── per-trade excursion ───────────────────────────────────────────────────────

def _excursions(trades: Sequence[Trade], df: pd.DataFrame) -> dict[int, tuple[float, float]]:
    """
    Maximum adverse and favourable excursion for each trade.

    MAE is the worst unrealised loss while the position was open; MFE is the best
    unrealised gain. Together they answer questions a P&L column cannot: whether
    winners were ever deeply underwater, and how much open profit was handed back.
    """
    out: dict[int, tuple[float, float]] = {}
    idx = df.index
    high, low = df["high"], df["low"]
    for i, t in enumerate(trades):
        try:
            lo_pos = idx.get_loc(t.entry_time)
            hi_pos = idx.get_loc(t.exit_time)
        except KeyError:
            out[i] = (0.0, 0.0)
            continue
        if hi_pos <= lo_pos:
            out[i] = (0.0, 0.0)
            continue
        window_hi = float(high.iloc[lo_pos:hi_pos + 1].max())
        window_lo = float(low.iloc[lo_pos:hi_pos + 1].min())
        entry = t.entry_price
        if entry <= 0:
            out[i] = (0.0, 0.0)
            continue
        if t.direction == "LONG":
            mfe = (window_hi / entry - 1.0) * 100
            mae = (window_lo / entry - 1.0) * 100
        else:
            mfe = (1.0 - window_lo / entry) * 100
            mae = (1.0 - window_hi / entry) * 100
        out[i] = (min(0.0, mae), max(0.0, mfe))
    return out


def _side_stats(side: str, trades: Sequence[Trade], excursions: dict[int, tuple[float, float]],
                indices: Sequence[int], cost_pct: float) -> SideStats:
    s = SideStats(side=side)
    if not trades:
        return s

    rets = [t.net_return * 100 for t in trades]
    bars = [t.bars_held for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]

    s.total_trades = len(trades)
    s.winning_trades = len(wins)
    s.losing_trades = len(losses)
    s.percent_profitable = len(wins) / len(trades) * 100

    s.gross_profit_pct = float(sum(wins))
    s.gross_loss_pct = float(abs(sum(losses)))
    s.net_profit_pct = s.gross_profit_pct - s.gross_loss_pct
    s.profit_factor = (s.gross_profit_pct / s.gross_loss_pct
                       if s.gross_loss_pct > 1e-12
                       else (float("inf") if s.gross_profit_pct > 0 else float("nan")))

    s.avg_trade_pct = float(np.mean(rets))
    s.avg_win_pct = float(np.mean(wins)) if wins else 0.0
    s.avg_loss_pct = float(np.mean(losses)) if losses else 0.0
    s.win_loss_ratio = (abs(s.avg_win_pct / s.avg_loss_pct)
                        if abs(s.avg_loss_pct) > 1e-12 else float("nan"))

    s.largest_win_pct = float(max(rets))
    s.largest_loss_pct = float(min(rets))

    s.avg_bars = float(np.mean(bars))
    win_bars = [b for b, r in zip(bars, rets) if r > 0]
    loss_bars = [b for b, r in zip(bars, rets) if r <= 0]
    s.avg_bars_winning = float(np.mean(win_bars)) if win_bars else 0.0
    s.avg_bars_losing = float(np.mean(loss_bars)) if loss_bars else 0.0

    # Longest unbroken runs of wins and losses.
    best_w = best_l = cur_w = cur_l = 0
    for r in rets:
        if r > 0:
            cur_w, cur_l = cur_w + 1, 0
        else:
            cur_l, cur_w = cur_l + 1, 0
        best_w, best_l = max(best_w, cur_w), max(best_l, cur_l)
    s.max_consecutive_wins, s.max_consecutive_losses = best_w, best_l

    maes = [excursions.get(i, (0.0, 0.0))[0] for i in indices]
    mfes = [excursions.get(i, (0.0, 0.0))[1] for i in indices]
    s.avg_mae_pct = float(np.mean(maes)) if maes else 0.0
    s.avg_mfe_pct = float(np.mean(mfes)) if mfes else 0.0

    # Both legs of every trade pay the modelled cost.
    s.commission_paid_pct = len(trades) * cost_pct * 2 * 100
    return s


# ── equity-curve statistics ───────────────────────────────────────────────────

def _drawdown_and_runup(equity: pd.Series) -> tuple[float, int, float, int, Optional[int]]:
    """
    Worst drawdown and best run-up, with their durations in bars.

    Run-up is the mirror of drawdown — the largest rise from a trough — and is
    what TradingView reports as *Max Run-up*. Recovery time is the number of bars
    from the drawdown trough back to the prior peak, or None if never recovered.
    """
    v = equity.to_numpy(dtype=float)
    if len(v) < 2:
        return 0.0, 0, 0.0, 0, None

    peak = np.maximum.accumulate(v)
    trough = np.minimum.accumulate(v)
    dd = v / peak - 1.0
    ru = v / trough - 1.0

    max_dd = float(dd.min())
    dd_end = int(dd.argmin())
    dd_start = int(np.argmax(v[:dd_end + 1])) if dd_end > 0 else 0
    dd_bars = dd_end - dd_start

    max_ru = float(ru.max())
    ru_end = int(ru.argmax())
    ru_start = int(np.argmin(v[:ru_end + 1])) if ru_end > 0 else 0
    ru_bars = ru_end - ru_start

    recover = None
    if dd_end < len(v) - 1:
        target = v[dd_start]
        after = np.flatnonzero(v[dd_end:] >= target)
        if len(after):
            recover = int(after[0])

    return max_dd * 100, dd_bars, max_ru * 100, ru_bars, recover


def _risk_metrics(equity: pd.Series, net: pd.Series, position: Optional[pd.Series],
                  bars_per_year: int) -> RiskMetrics:
    m = RiskMetrics()
    r = net.dropna()
    if len(r) < 5 or equity.empty:
        return m

    n = len(r)
    m.annualised_reliable = n >= MIN_BARS_FOR_ANNUALISED
    years = max(n / bars_per_year, 1e-9)
    final = float(equity.iloc[-1])

    m.cagr_pct = ((final ** (1 / years) - 1) * 100) if final > 0 else -100.0
    m.volatility_pct = _safe(r.std(ddof=0) * math.sqrt(bars_per_year) * 100)
    downside = r[r < 0]
    m.downside_deviation_pct = _safe(downside.std(ddof=0) * math.sqrt(bars_per_year) * 100)

    mean_ann = float(r.mean()) * bars_per_year
    m.sharpe = _safe(mean_ann / (m.volatility_pct / 100)) if m.volatility_pct > 1e-9 else 0.0
    m.sortino = (_safe(mean_ann / (m.downside_deviation_pct / 100))
                 if m.downside_deviation_pct > 1e-9 else 0.0)

    dd_pct, dd_bars, ru_pct, ru_bars, recover = _drawdown_and_runup(equity)
    m.max_drawdown_pct, m.max_drawdown_bars = dd_pct, dd_bars
    m.max_runup_pct, m.max_runup_bars = ru_pct, ru_bars
    m.time_to_recover_bars = recover

    m.calmar = _safe(m.cagr_pct / abs(dd_pct)) if abs(dd_pct) > 1e-9 else 0.0
    net_profit = (final - 1.0) * 100
    m.recovery_factor = _safe(net_profit / abs(dd_pct)) if abs(dd_pct) > 1e-9 else float("nan")

    # Omega at a zero threshold: gains over losses, probability-weighted
    # (Keating & Shadwick 2002).
    gains = r[r > 0].sum()
    pains = abs(r[r < 0].sum())
    m.omega = _safe(gains / pains, float("nan")) if pains > 1e-12 else float("nan")

    # Ulcer Index (Martin & McCann 1989) and the Martin/UPI ratio built on it.
    dd_series = (equity / equity.cummax() - 1.0) * 100
    m.ulcer_index = _safe(math.sqrt(float((dd_series ** 2).mean())))
    m.martin_ratio = _safe(m.cagr_pct / m.ulcer_index, float("nan")) if m.ulcer_index > 1e-9 else float("nan")

    # K-ratio (Kestner): t-statistic of the log-equity regression slope, then
    # normalised by sample length so the value is comparable across histories of
    # different length. Written as `t / sqrt(n)` — multiplying by sqrt(n) instead
    # produces numbers in the thousands, which is not what the ratio means; a
    # healthy K-ratio is order 0–3.
    try:
        y = np.log(equity.clip(lower=1e-9).to_numpy())
        n_obs = len(y)
        x = np.arange(n_obs, dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        resid = y - (slope * x + intercept)
        se = math.sqrt(float((resid ** 2).sum()) / max(1, n_obs - 2)) / \
            math.sqrt(float(((x - x.mean()) ** 2).sum()))
        m.k_ratio = (_safe(slope / se / math.sqrt(n_obs), float("nan"))
                     if se > 1e-15 and n_obs > 2 else float("nan"))
    except Exception:
        m.k_ratio = float("nan")

    m.var_95_pct = _safe(float(r.quantile(0.05)) * 100)
    tail = r[r <= r.quantile(0.05)]
    m.cvar_95_pct = _safe(float(tail.mean()) * 100) if len(tail) else 0.0

    hi, lo = float(r.quantile(0.95)), float(r.quantile(0.05))
    m.tail_ratio = _safe(abs(hi) / abs(lo), float("nan")) if abs(lo) > 1e-12 else float("nan")

    m.skew = _safe(float(r.skew()))
    m.excess_kurtosis = _safe(float(r.kurt()))
    m.best_bar_pct = _safe(float(r.max()) * 100)
    m.worst_bar_pct = _safe(float(r.min()) * 100)
    m.positive_bars_pct = _safe(float((r > 0).mean()) * 100)
    if position is not None and len(position):
        m.time_in_market_pct = _safe(float((position.abs() > 1e-9).mean()) * 100)
    return m


def _monthly_returns(equity: pd.Series) -> dict:
    """Calendar-month returns, as TradingView's monthly performance grid."""
    if not isinstance(equity.index, pd.DatetimeIndex) or len(equity) < 2:
        return {}
    monthly = equity.resample("ME").last().pct_change().dropna()
    out: dict = {}
    for ts, val in monthly.items():
        out.setdefault(str(ts.year), {})[ts.strftime("%b")] = round(float(val) * 100, 3)
    yearly = equity.resample("YE").last().pct_change().dropna()
    for ts, val in yearly.items():
        out.setdefault(str(ts.year), {})["YEAR"] = round(float(val) * 100, 3)
    return out


# ── entry point ───────────────────────────────────────────────────────────────

def analyse(result: BacktestResult, df: pd.DataFrame, *, bars_per_year: int = 252,
            initial_capital: float = 100_000.0, commission_pct: float = 0.05,
            slippage_pct: float = 0.05,
            position: Optional[pd.Series] = None) -> PerformanceReport:
    """Build the full report from a completed backtest."""
    trades = list(result.trades)
    equity = result.equity_curve
    net = equity.pct_change().fillna(0.0) if len(equity) else pd.Series(dtype=float)

    exc = _excursions(trades, df)
    long_idx = [i for i, t in enumerate(trades) if t.direction == "LONG"]
    short_idx = [i for i, t in enumerate(trades) if t.direction == "SHORT"]
    cost = (commission_pct + slippage_pct) / 100.0

    report = PerformanceReport(
        strategy=result.strategy, symbol=result.symbol, interval=result.interval,
        bars=result.bars,
        period_start=str(df.index[0]) if len(df) else "",
        period_end=str(df.index[-1]) if len(df) else "",
        all_trades=_side_stats("All", trades, exc, list(range(len(trades))), cost),
        long_trades=_side_stats("Long", [trades[i] for i in long_idx], exc, long_idx, cost),
        short_trades=_side_stats("Short", [trades[i] for i in short_idx], exc, short_idx, cost),
        risk=_risk_metrics(equity, net, position, bars_per_year),
        buy_and_hold_pct=result.buy_and_hold_pct,
        excess_return_pct=result.excess_return_pct,
        initial_capital=initial_capital,
        commission_pct=commission_pct, slippage_pct=slippage_pct,
        monthly_returns=_monthly_returns(equity),
        equity_curve=equity)

    # Caveats are part of the result, not a footnote. A profit factor computed on
    # six trades is not a comparable number to one computed on six hundred.
    a = report.all_trades
    if 0 < a.total_trades < MIN_TRADES_FOR_CONFIDENCE:
        report.caveats.append(
            f"Only {a.total_trades} trades — trade-based ratios (profit factor, win rate, "
            f"expectancy) are not statistically meaningful below ~{MIN_TRADES_FOR_CONFIDENCE}.")
    if a.total_trades == 0:
        report.caveats.append("No trades were taken; every trade statistic is undefined.")
    if not report.risk.annualised_reliable:
        report.caveats.append(
            f"Only {result.bars} bars — CAGR, Sharpe and Sortino are annualised from a short "
            f"sample and will overstate their own precision.")
    if abs(report.risk.max_drawdown_pct) < 0.5 and a.total_trades > 0:
        report.caveats.append(
            "Max drawdown is under 0.5%, so Calmar, recovery factor and the Martin ratio "
            "divide by a near-zero denominator and are not informative.")
    if report.long_trades.total_trades and report.short_trades.total_trades:
        ln, sn = report.long_trades.net_profit_pct, report.short_trades.net_profit_pct
        if ln > 0 > sn:
            report.caveats.append(
                f"All profit comes from the long side (+{ln:.1f}%); the short side loses "
                f"{sn:.1f}%. Consider running it long-only.")
        elif sn > 0 > ln:
            report.caveats.append(
                f"All profit comes from the short side (+{sn:.1f}%); the long side loses "
                f"{ln:.1f}%.")
    if a.total_trades and a.largest_win_pct > 0 and a.gross_profit_pct > 0:
        share = a.largest_win_pct / a.gross_profit_pct * 100
        if share > 40:
            report.caveats.append(
                f"A single trade produced {share:.0f}% of all gross profit — the result rests "
                f"on one outcome, not on a repeatable edge.")
    return report


# ── rendering ─────────────────────────────────────────────────────────────────

def _fmt(x: float, suffix: str = "", dp: int = 2) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "—"
    return f"{x:,.{dp}f}{suffix}"


def render_markdown(rep: PerformanceReport) -> str:
    """Render the report in the layout of TradingView's Performance Summary."""
    a, l, s, r = rep.all_trades, rep.long_trades, rep.short_trades, rep.risk

    lines = [
        f"# Strategy performance — {rep.strategy}",
        "",
        f"**{rep.symbol} · {rep.interval}** · {rep.bars} bars · "
        f"{rep.period_start[:10]} → {rep.period_end[:10]}",
        f"_Costs: {rep.commission_pct:.3f}% commission + {rep.slippage_pct:.3f}% slippage, "
        f"charged both legs._",
        "",
        "## Overview",
        "",
        "| | Value |",
        "|---|---:|",
        f"| Net profit | **{_fmt(a.net_profit_pct, '%')}** |",
        f"| Buy & hold return | {_fmt(rep.buy_and_hold_pct, '%')} |",
        f"| **Excess over buy & hold** | **{_fmt(rep.excess_return_pct, '%')}** |",
        f"| CAGR | {_fmt(r.cagr_pct, '%')} |",
        f"| Max drawdown | {_fmt(r.max_drawdown_pct, '%')} (over {r.max_drawdown_bars} bars) |",
        f"| Max run-up | {_fmt(r.max_runup_pct, '%')} (over {r.max_runup_bars} bars) |",
        f"| Time to recover | {r.time_to_recover_bars if r.time_to_recover_bars is not None else 'not recovered'} bars |",
        f"| Total closed trades | {a.total_trades} |",
        f"| Percent profitable | {_fmt(a.percent_profitable, '%')} |",
        f"| Profit factor | {_fmt(a.profit_factor)} |",
        f"| Commission paid | {_fmt(a.commission_paid_pct, '%')} |",
        f"| Time in market | {_fmt(r.time_in_market_pct, '%')} |",
        "",
        "## Performance summary",
        "",
        "| Metric | All | Long | Short |",
        "|---|---:|---:|---:|",
    ]

    rows = [
        ("Net profit %", "net_profit_pct", "%"), ("Gross profit %", "gross_profit_pct", "%"),
        ("Gross loss %", "gross_loss_pct", "%"), ("Profit factor", "profit_factor", ""),
        ("Total trades", "total_trades", ""), ("Winning trades", "winning_trades", ""),
        ("Losing trades", "losing_trades", ""), ("Percent profitable", "percent_profitable", "%"),
        ("Avg trade %", "avg_trade_pct", "%"), ("Avg winning trade %", "avg_win_pct", "%"),
        ("Avg losing trade %", "avg_loss_pct", "%"), ("Ratio avg win / avg loss", "win_loss_ratio", ""),
        ("Largest win %", "largest_win_pct", "%"), ("Largest loss %", "largest_loss_pct", "%"),
        ("Avg bars in trade", "avg_bars", ""), ("Avg bars in winners", "avg_bars_winning", ""),
        ("Avg bars in losers", "avg_bars_losing", ""),
        ("Max consecutive wins", "max_consecutive_wins", ""),
        ("Max consecutive losses", "max_consecutive_losses", ""),
        ("Avg MAE %", "avg_mae_pct", "%"), ("Avg MFE %", "avg_mfe_pct", "%"),
    ]
    for label, attr, suf in rows:
        vals = []
        for side in (a, l, s):
            v = getattr(side, attr)
            vals.append(f"{v:,}" if isinstance(v, int) else _fmt(v, suf))
        lines.append(f"| {label} | {vals[0]} | {vals[1]} | {vals[2]} |")

    lines += [
        "",
        "## Risk & return ratios",
        "",
        "| Ratio | Value | What it measures |",
        "|---|---:|---|",
        f"| Sharpe | {_fmt(r.sharpe)} | Return per unit of total volatility |",
        f"| Sortino | {_fmt(r.sortino)} | Return per unit of *downside* volatility |",
        f"| Calmar | {_fmt(r.calmar)} | CAGR per unit of max drawdown |",
        f"| Omega | {_fmt(r.omega)} | Total gains ÷ total losses (Keating & Shadwick 2002) |",
        f"| Martin (UPI) | {_fmt(r.martin_ratio)} | CAGR ÷ Ulcer Index — penalises deep, long drawdowns |",
        f"| K-ratio | {_fmt(r.k_ratio)} | Consistency of the equity climb (Kestner 1996) |",
        f"| Recovery factor | {_fmt(r.recovery_factor)} | Net profit ÷ max drawdown |",
        f"| Ulcer Index | {_fmt(r.ulcer_index)} | RMS drawdown — depth *and* duration |",
        f"| Tail ratio | {_fmt(r.tail_ratio)} | 95th percentile gain ÷ 5th percentile loss |",
        "",
        "| Distribution | Value |",
        "|---|---:|",
        f"| Annualised volatility | {_fmt(r.volatility_pct, '%')} |",
        f"| Downside deviation | {_fmt(r.downside_deviation_pct, '%')} |",
        f"| VaR 95% (per bar) | {_fmt(r.var_95_pct, '%')} |",
        f"| CVaR 95% (per bar) | {_fmt(r.cvar_95_pct, '%')} |",
        f"| Skew | {_fmt(r.skew)} |",
        f"| Excess kurtosis | {_fmt(r.excess_kurtosis)} |",
        f"| Best bar | {_fmt(r.best_bar_pct, '%')} |",
        f"| Worst bar | {_fmt(r.worst_bar_pct, '%')} |",
        f"| Positive bars | {_fmt(r.positive_bars_pct, '%')} |",
    ]

    if rep.monthly_returns:
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        lines += ["", "## Monthly returns (%)", "",
                  "| Year | " + " | ".join(months) + " | **Year** |",
                  "|---|" + "---:|" * 13]
        for year in sorted(rep.monthly_returns):
            row = rep.monthly_returns[year]
            cells = [f"{row[m]:+.1f}" if m in row else "—" for m in months]
            yr = f"**{row['YEAR']:+.1f}**" if "YEAR" in row else "—"
            lines.append(f"| {year} | " + " | ".join(cells) + f" | {yr} |")

    if rep.caveats:
        lines += ["", "## Read this before trusting the numbers above", ""]
        lines += [f"- {c}" for c in rep.caveats]

    lines += ["", "---", "",
              "_Backtested on historical data with modelled costs. Signals act on the bar "
              "after they are generated. Past performance does not predict future results._"]
    return "\n".join(lines)
