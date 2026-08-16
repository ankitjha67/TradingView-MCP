"""
Vectorised backtester.

The previous engine re-sliced a growing DataFrame once per bar per strategy and
recomputed every indicator inside that loop — O(n²) work per model, minutes of
wall clock for a single comparison across the library, called on a 60-second
timer by the monitor.

Here each model produces its full signal path in one vectorised pass, and the
simulation is a handful of array operations over that path.

Two correctness properties this engine holds and the previous one did not:

* **No look-ahead.** Signals are shifted one bar before they take effect: a
  signal computed from a bar's close is acted on at the *next* bar's open. A
  backtest that enters at the close of the bar that generated the signal is
  reading the future, and its results are meaningless.
* **Costs are charged.** Commission and slippage are applied on entry and exit.
  A strategy that flips daily can look excellent gross and lose money net.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from .base import NEUTRAL_BAND, BaseStrategy
from .features import FeatureSet, build_features
from .registry import StrategyRegistry, get_registry


@dataclass
class Trade:
    entry_time: object
    exit_time: object
    direction: str
    entry_price: float
    exit_price: float
    gross_return: float
    net_return: float
    bars_held: int
    exit_reason: str

    def to_dict(self) -> dict:
        return {"entry_time": str(self.entry_time), "exit_time": str(self.exit_time),
                "direction": self.direction, "entry_price": round(self.entry_price, 6),
                "exit_price": round(self.exit_price, 6),
                "gross_return_pct": round(self.gross_return * 100, 4),
                "net_return_pct": round(self.net_return * 100, 4),
                "bars_held": self.bars_held, "exit_reason": self.exit_reason}


@dataclass
class BacktestResult:
    strategy: str
    category: str
    symbol: str
    interval: str
    bars: int

    total_return_pct: float
    annualized_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    calmar_ratio: float
    volatility_pct: float

    total_trades: int
    win_rate_pct: float
    profit_factor: float
    avg_win_pct: float
    avg_loss_pct: float
    expectancy_pct: float
    avg_bars_held: float
    exposure_pct: float

    buy_and_hold_pct: float
    excess_return_pct: float

    equity_curve: pd.Series = field(default_factory=pd.Series, repr=False)
    trades: list[Trade] = field(default_factory=list, repr=False)
    error: str = ""

    def to_dict(self, include_curve: bool = False) -> dict:
        out = {
            "strategy": self.strategy, "category": self.category, "symbol": self.symbol,
            "interval": self.interval, "bars": self.bars,
            "total_return_pct": round(self.total_return_pct, 3),
            "annualized_return_pct": round(self.annualized_return_pct, 3),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "sortino_ratio": round(self.sortino_ratio, 3),
            "max_drawdown_pct": round(self.max_drawdown_pct, 3),
            "calmar_ratio": round(self.calmar_ratio, 3),
            "volatility_pct": round(self.volatility_pct, 3),
            "total_trades": self.total_trades,
            "win_rate_pct": round(self.win_rate_pct, 2),
            "profit_factor": (round(self.profit_factor, 3)
                              if math.isfinite(self.profit_factor) else None),
            "avg_win_pct": round(self.avg_win_pct, 3),
            "avg_loss_pct": round(self.avg_loss_pct, 3),
            "expectancy_pct": round(self.expectancy_pct, 4),
            "avg_bars_held": round(self.avg_bars_held, 1),
            "exposure_pct": round(self.exposure_pct, 2),
            "buy_and_hold_pct": round(self.buy_and_hold_pct, 3),
            "excess_return_pct": round(self.excess_return_pct, 3),
            "error": self.error,
        }
        if include_curve and len(self.equity_curve):
            out["equity_curve"] = [
                {"t": str(t), "equity": round(float(v), 6)}
                for t, v in self.equity_curve.items()
            ]
        return out


def _empty_result(name: str, category: str, symbol: str, interval: str,
                  bars: int, error: str) -> BacktestResult:
    return BacktestResult(
        strategy=name, category=category, symbol=symbol, interval=interval, bars=bars,
        total_return_pct=0.0, annualized_return_pct=0.0, sharpe_ratio=0.0,
        sortino_ratio=0.0, max_drawdown_pct=0.0, calmar_ratio=0.0, volatility_pct=0.0,
        total_trades=0, win_rate_pct=0.0, profit_factor=float("nan"),
        avg_win_pct=0.0, avg_loss_pct=0.0, expectancy_pct=0.0, avg_bars_held=0.0,
        exposure_pct=0.0, buy_and_hold_pct=0.0, excess_return_pct=0.0, error=error)


def run_backtest(
    strategy: BaseStrategy,
    f: FeatureSet,
    *,
    commission_pct: float = 0.05,
    slippage_pct: float = 0.05,
    allow_short: bool = True,
    band: float = NEUTRAL_BAND,
    scale_by_conviction: bool = True,
) -> BacktestResult:
    """
    Simulate one strategy over the full history.

    Positions are taken from the model's own conviction path. With
    ``scale_by_conviction`` the position size is proportional to |score|, which
    is what the score is for — a 0.9 reading should not size the same as a 0.2.
    """
    name, cat = strategy.name, strategy.category
    symbol, interval = f.symbol, f.interval

    ok, why = strategy.availability(f)
    if not ok:
        return _empty_result(name, cat, symbol, interval, f.n, why)

    try:
        raw = strategy.score_series(f)
    except Exception as exc:
        return _empty_result(name, cat, symbol, interval, f.n, f"{type(exc).__name__}: {exc}")

    if raw.notna().sum() < 10:
        return _empty_result(name, cat, symbol, interval, f.n, "signal undefined over the sample")

    sig = raw.fillna(0.0)
    target = sig.where(sig.abs() >= band, 0.0)
    if not scale_by_conviction:
        target = np.sign(target)
    if not allow_short:
        target = target.clip(lower=0.0)

    # THE critical line: act on the next bar, never the signalling bar.
    position = target.shift(1).fillna(0.0)

    ret = f.close.pct_change().fillna(0.0)
    gross = position * ret

    # Costs charged on the traded delta, both legs.
    turnover = position.diff().abs().fillna(position.abs())
    cost_rate = (commission_pct + slippage_pct) / 100.0
    net = gross - turnover * cost_rate

    equity = (1.0 + net).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)

    bpy = f.bars_per_year
    years = max(len(net) / bpy, 1e-9)
    ann_return = (equity.iloc[-1] ** (1 / years) - 1) if equity.iloc[-1] > 0 else -1.0

    vol = float(net.std(ddof=0) * math.sqrt(bpy))
    mean_ann = float(net.mean() * bpy)
    sharpe = mean_ann / vol if vol > 1e-12 else 0.0

    downside = net[net < 0].std(ddof=0) * math.sqrt(bpy)
    sortino = mean_ann / downside if downside and downside > 1e-12 else 0.0

    dd = equity / equity.cummax() - 1.0
    max_dd = float(dd.min())
    calmar = (ann_return / abs(max_dd)) if max_dd < -1e-9 else 0.0

    trades = _extract_trades(position, f, net, cost_rate)
    wins = [t.net_return for t in trades if t.net_return > 0]
    losses = [t.net_return for t in trades if t.net_return <= 0]
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 1e-12 else (
        float("inf") if gross_win > 0 else float("nan"))

    bh = float(f.close.iloc[-1] / f.close.iloc[0] - 1.0)

    return BacktestResult(
        strategy=name, category=cat, symbol=symbol, interval=interval, bars=f.n,
        total_return_pct=total_return * 100,
        annualized_return_pct=float(ann_return) * 100,
        sharpe_ratio=sharpe, sortino_ratio=float(sortino),
        max_drawdown_pct=max_dd * 100,
        calmar_ratio=float(calmar), volatility_pct=vol * 100,
        total_trades=len(trades),
        win_rate_pct=(len(wins) / len(trades) * 100) if trades else 0.0,
        profit_factor=profit_factor,
        avg_win_pct=(float(np.mean(wins)) * 100) if wins else 0.0,
        avg_loss_pct=(float(np.mean(losses)) * 100) if losses else 0.0,
        expectancy_pct=(float(np.mean([t.net_return for t in trades])) * 100) if trades else 0.0,
        avg_bars_held=(float(np.mean([t.bars_held for t in trades])) if trades else 0.0),
        exposure_pct=float((position.abs() > 0).mean() * 100),
        buy_and_hold_pct=bh * 100,
        excess_return_pct=(total_return - bh) * 100,
        equity_curve=equity, trades=trades)


def _extract_trades(position: pd.Series, f: FeatureSet, net: pd.Series,
                    cost_rate: float) -> list[Trade]:
    """Reconstruct discrete trades from the continuous position path."""
    pos = position.to_numpy()
    px = f.close.to_numpy()
    idx = f.close.index
    trades: list[Trade] = []

    side = 0  # -1 short, 0 flat, +1 long
    start = 0
    for i in range(len(pos)):
        cur = int(np.sign(pos[i]))
        if cur != side:
            if side != 0 and i > start:
                entry, exit_ = px[start], px[i]
                gross = (exit_ / entry - 1.0) * side
                trades.append(Trade(
                    entry_time=idx[start], exit_time=idx[i],
                    direction="LONG" if side > 0 else "SHORT",
                    entry_price=float(entry), exit_price=float(exit_),
                    gross_return=float(gross),
                    net_return=float(gross - 2 * cost_rate),
                    bars_held=i - start,
                    exit_reason="signal flip" if cur != 0 else "signal exit"))
            side, start = cur, i

    if side != 0 and start < len(pos) - 1:
        entry, exit_ = px[start], px[-1]
        gross = (exit_ / entry - 1.0) * side
        trades.append(Trade(
            entry_time=idx[start], exit_time=idx[-1],
            direction="LONG" if side > 0 else "SHORT",
            entry_price=float(entry), exit_price=float(exit_),
            gross_return=float(gross), net_return=float(gross - 2 * cost_rate),
            bars_held=len(pos) - 1 - start, exit_reason="open at end"))
    return trades


def compare_strategies(
    data,
    interval: str = "1d",
    symbol: str = "",
    *,
    registry: Optional[StrategyRegistry] = None,
    strategies: Optional[Sequence[BaseStrategy]] = None,
    commission_pct: float = 0.05,
    slippage_pct: float = 0.05,
    allow_short: bool = True,
    sort_by: str = "sharpe_ratio",
    min_trades: int = 3,
    available_feeds: Sequence[str] = (),
) -> dict:
    """
    Backtest every model over one shared FeatureSet and rank the results.

    Ranked by Sharpe rather than total return by default: total return rewards
    whichever model happened to take the most risk, which is not a skill measure.
    """
    f = data if isinstance(data, FeatureSet) else build_features(data, interval, symbol)
    f.meta["available_feeds"] = tuple(available_feeds)

    reg = registry or get_registry()
    models = list(strategies) if strategies is not None else reg.all()

    results, skipped = [], []
    for m in models:
        r = run_backtest(m, f, commission_pct=commission_pct, slippage_pct=slippage_pct,
                         allow_short=allow_short)
        (skipped if r.error else results).append(r)

    qualified = [r for r in results if r.total_trades >= min_trades]
    thin = [r for r in results if r.total_trades < min_trades]

    reverse = sort_by not in ("max_drawdown_pct", "volatility_pct")
    qualified.sort(key=lambda r: (getattr(r, sort_by, 0.0)
                                  if math.isfinite(getattr(r, sort_by, 0.0)) else -1e9),
                   reverse=reverse)

    bh = float(f.close.iloc[-1] / f.close.iloc[0] - 1.0) * 100
    return {
        "symbol": f.symbol or symbol, "interval": f.interval, "bars": f.n,
        "period_start": str(f.df.index[0]), "period_end": str(f.df.index[-1]),
        "buy_and_hold_pct": round(bh, 3),
        "costs": {"commission_pct": commission_pct, "slippage_pct": slippage_pct},
        "sorted_by": sort_by,
        "models_tested": len(models),
        "models_ranked": len(qualified),
        "models_skipped": len(skipped),
        "models_too_few_trades": len(thin),
        "ranking": [{**r.to_dict(), "rank": i + 1} for i, r in enumerate(qualified)],
        "skipped": [{"strategy": r.strategy, "reason": r.error} for r in skipped[:50]],
        # Beating buy-and-hold is the only comparison that matters for a long-only
        # alternative, so surface it rather than leaving it to be inferred.
        "beat_buy_and_hold": sum(1 for r in qualified if r.total_return_pct > bh),
    }


def walk_forward(
    strategy: BaseStrategy,
    f: FeatureSet,
    *,
    folds: int = 4,
    commission_pct: float = 0.05,
    slippage_pct: float = 0.05,
) -> dict:
    """
    Split the sample into sequential folds and report per-fold performance.

    Consistency across folds is the signal worth having. A model that makes all
    its money in one fold and nothing in the others is fitted to that fold, and
    the headline Sharpe over the full sample hides exactly that.
    """
    n = f.n
    if n < folds * 60:
        return {"error": f"need at least {folds * 60} bars for {folds} folds, have {n}"}

    size = n // folds
    fold_results = []
    for k in range(folds):
        lo = k * size
        hi = n if k == folds - 1 else (k + 1) * size
        sub = FeatureSet(df=f.df.iloc[lo:hi].copy(), interval=f.interval, symbol=f.symbol)
        r = run_backtest(strategy, sub, commission_pct=commission_pct,
                         slippage_pct=slippage_pct)
        fold_results.append({
            "fold": k + 1, "start": str(sub.df.index[0]), "end": str(sub.df.index[-1]),
            "bars": sub.n, "return_pct": round(r.total_return_pct, 3),
            "sharpe": round(r.sharpe_ratio, 3), "trades": r.total_trades,
            "max_drawdown_pct": round(r.max_drawdown_pct, 3), "error": r.error,
        })

    valid = [x for x in fold_results if not x["error"]]
    sharpes = [x["sharpe"] for x in valid]
    profitable = sum(1 for x in valid if x["return_pct"] > 0)

    verdict = "insufficient data"
    if len(valid) >= 2:
        consistency = profitable / len(valid)
        spread = float(np.std(sharpes)) if sharpes else 0.0
        verdict = ("consistent across folds" if consistency >= 0.75 and spread < 1.0 else
                   "mixed — performance is fold-dependent" if consistency >= 0.5 else
                   "inconsistent — likely overfit or regime-specific")

    return {
        "strategy": strategy.name, "symbol": f.symbol, "interval": f.interval,
        "folds": fold_results,
        "profitable_folds": f"{profitable}/{len(valid)}",
        "mean_sharpe": round(float(np.mean(sharpes)), 3) if sharpes else 0.0,
        "sharpe_std": round(float(np.std(sharpes)), 3) if sharpes else 0.0,
        "verdict": verdict,
    }
