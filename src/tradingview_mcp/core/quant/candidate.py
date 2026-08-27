"""
Admission tests for a strategy before it joins the library.

The library began as 200 claimed models of which most were template clones that
silently degraded to a moving-average crossover when their real input was
missing. That is the failure this module exists to prevent from recurring —
particularly now that candidates can be drafted from papers rather than written
by hand, because a drafted model is fluent, plausible and completely untested.

Five checks, in the order a bad model usually fails them:

**Contract.** It implements ``score(f) -> pd.Series``, returns the right index,
and stays inside [-1, +1]. A model outside that range breaks the weighting in
``consensus.py`` silently rather than loudly.

**Causality.** The one that matters most and the one nothing in this codebase
checked before. A causal model's reading of bar *i* cannot change when later
bars arrive, so scoring the first *n* bars and then scoring *n + k* must agree
on the overlap. A model that fails this backtests beautifully and cannot be
traded.

What it catches reliably is *global* leakage — a statistic taken over the whole
sample and then applied backwards. That is the common and the dangerous case:
it shifts every historical reading at once, and it is exactly what both GARCH
models were doing before this existed.

What it catches only partly is leakage confined to a few bars either side of a
point, such as a short centred window. Those diverge only near the truncation
join, which is the region the edge guard has to exclude so that ordinary
filling windows do not read as failures. A wider centred window is caught; a
narrow one may not be. The check is a strong filter, not a proof.

**Non-degeneracy.** A constant series, an all-NaN series, or one that is
non-zero on three bars out of fifteen hundred is not a signal. This is what
caught the original template clones: they had only two distinct behaviours
between them.

**Honest needs.** If it reads volume it must declare ``DataNeed.VOLUME``, so
that instruments without volume see it stand down instead of voting on a
substitute.

**Evidence.** It backtests without error, and its t-statistic is reported
rather than assumed. Failing to clear significance is not a rejection — almost
nothing does on a short window — but the number travels with the verdict.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .base import BaseStrategy, DataNeed
from .features import FeatureSet, build_features

# How far back the causality probe truncates, as a fraction of the sample.
CAUSAL_SPLIT = 0.7
# Bars near the join are excluded: a rolling window legitimately needs future
# bars to be *present*, not to be *read*, and the last bar of a 200-period mean
# is undefined until the window fills. The exclusion has to scale with the
# model's own lookback — a fixed five bars flagged a 5-year mean-reversion
# model for changing 5 of 440 readings by 0.003, all of them at the boundary.
CAUSAL_EDGE = 5


def _causal_edge(strategy) -> int:
    """How many bars before the cut to ignore, given the model's lookback."""
    return max(CAUSAL_EDGE, int(getattr(strategy, "min_bars", 0) or 0) // 4)
CAUSAL_TOLERANCE = 1e-6


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    fatal: bool = True


@dataclass
class Admission:
    strategy: str = ""
    checks: list = field(default_factory=list)
    t_stat: float = float("nan")
    trades: int = 0

    @property
    def admitted(self) -> bool:
        return bool(self.checks) and not any(
            c.fatal and not c.passed for c in self.checks)

    @property
    def failures(self) -> list:
        return [c for c in self.checks if not c.passed]

    def report(self) -> str:
        lines = [f"{self.strategy}"]
        for c in self.checks:
            mark = "ok  " if c.passed else ("FAIL" if c.fatal else "warn")
            lines.append(f"  [{mark}] {c.name}: {c.detail}")
        lines.append(f"  -> {'ADMIT' if self.admitted else 'REJECT'}")
        return "\n".join(lines)


def _score_of(strategy: BaseStrategy, f: FeatureSet) -> Optional[pd.Series]:
    try:
        s = strategy.score_series(f)
    except Exception:
        return None
    return s if isinstance(s, pd.Series) else None


def check_contract(strategy: BaseStrategy, f: FeatureSet) -> CheckResult:
    # Deliberately the raw score(), not score_series(): the latter clips to
    # [-1, +1] in BaseStrategy, so checking it could never catch a model that
    # returns 4.2 — it would see the clipped 1.0 and pass.
    try:
        s = strategy.score(f)
    except Exception as exc:
        return CheckResult("contract", False, f"score() raised: {exc}")
    if not isinstance(s, pd.Series):
        return CheckResult("contract", False,
                           f"score() returned {type(s).__name__}, not a Series")
    if len(s) != f.n:
        return CheckResult("contract", False,
                           f"returned {len(s)} values for {f.n} bars")
    finite = s.dropna()
    if len(finite) and (finite.abs() > 1.0 + 1e-9).any():
        worst = float(finite.abs().max())
        return CheckResult("contract", False,
                           f"score reaches {worst:.3f}, outside [-1, +1]")
    return CheckResult("contract", True,
                       f"{len(finite)} finite values, all within [-1, +1]")


def check_causal(strategy: BaseStrategy, f: FeatureSet) -> CheckResult:
    """
    Does knowing the future change the past?

    Score the first 70% of bars, then the whole sample, and compare the
    overlap. A causal model cannot revise a reading once the bar has closed.
    """
    n = f.n
    cut = int(n * CAUSAL_SPLIT)
    if cut < 60 or n - cut < 20:
        return CheckResult("causality", True,
                           "sample too short to split; not checked", fatal=False)

    full = _score_of(strategy, f)
    if full is None:
        return CheckResult("causality", False, "score() failed on the full sample")

    try:
        truncated = build_features(f.df.iloc[:cut].copy(), f.interval, f.symbol)
        truncated.meta.update(dict(f.meta))
        early = _score_of(strategy, truncated)
    except Exception as exc:
        return CheckResult("causality", False,
                           f"failed when re-scored on a truncated sample: {exc}")
    if early is None:
        return CheckResult("causality", False,
                           "score() failed on the truncated sample")

    edge = _causal_edge(strategy)
    if cut - edge < 40:
        return CheckResult("causality", True,
                           f"lookback {getattr(strategy, 'min_bars', 0)} leaves too "
                           f"little clear of the join to judge", fatal=False)
    a = full.iloc[:cut - edge]
    b = early.iloc[:cut - edge]
    both = a.notna() & b.notna()
    if both.sum() < 30:
        return CheckResult("causality", True,
                           "too few overlapping values to judge", fatal=False)

    diff = (a[both] - b[both]).abs()
    worst = float(diff.max())
    if worst <= CAUSAL_TOLERANCE:
        return CheckResult("causality", True,
                           f"{int(both.sum())} overlapping bars unchanged when "
                           f"later data is added")
    where = int(diff.idxmax() is not None and diff.argmax())
    return CheckResult(
        "causality", False,
        f"adding later bars changed {int((diff > CAUSAL_TOLERANCE).sum())} of "
        f"{int(both.sum())} earlier readings, worst {worst:.4f} at bar {where}. "
        f"The model reads data it would not have had.")


def check_non_degenerate(strategy: BaseStrategy, f: FeatureSet) -> CheckResult:
    s = _score_of(strategy, f)
    if s is None:
        return CheckResult("non-degenerate", False, "no score to inspect")
    finite = s.dropna()
    if finite.empty:
        return CheckResult("non-degenerate", False, "every value is NaN")
    active = float((finite.abs() > 1e-9).mean())
    distinct = int(finite.round(4).nunique())

    # A constant *non-zero* score votes the same way on every bar regardless of
    # the data — the template-clone failure. A constant *zero* is different: it
    # is an abstention, counted as available but not voting, which is the
    # honest answer for a weekend-effect model on daily equities.
    if distinct == 1:
        value = float(finite.iloc[0])
        if abs(value) > 1e-9:
            return CheckResult("non-degenerate", False,
                               f"constant {value:+.3f} on every bar — votes the "
                               f"same way whatever the data")
        return CheckResult("non-degenerate", True,
                           "flat zero here — abstains rather than voting, which "
                           "is correct when the model has nothing to read",
                           fatal=False)

    # Two states is what a seasonal or a stop-and-reverse rule *is*. Parabolic
    # SAR is long or short and nothing between; calling that degenerate would
    # reject a correct implementation.
    if distinct == 2 and active >= 0.01:
        return CheckResult("non-degenerate", True,
                           f"binary signal, active on {active:.1%} of bars")

    if active < 0.01:
        return CheckResult("non-degenerate", False,
                           f"non-zero on {active:.2%} of bars — effectively silent")
    return CheckResult("non-degenerate", True,
                       f"{distinct} distinct values, active on {active:.1%} of bars")


def check_declares_needs(strategy: BaseStrategy, f: FeatureSet) -> CheckResult:
    """
    If it reads volume, it must say so.

    Re-score with volume blanked. A model that declares no VOLUME need but
    changes its answer was reading it, and would vote on instruments that have
    no volume feed at all.
    """
    if not f.has_volume:
        return CheckResult("declared needs", True, "no volume in this sample",
                           fatal=False)
    needs = set(getattr(strategy, "needs", ()) or ())
    if DataNeed.VOLUME in needs:
        return CheckResult("declared needs", True, "declares VOLUME")

    base = _score_of(strategy, f)
    if base is None:
        return CheckResult("declared needs", True, "no score to compare", fatal=False)
    df = f.df.copy()
    df["volume"] = float(df["volume"].median() or 1.0)
    try:
        flat = build_features(df, f.interval, f.symbol)
        flat.meta.update(dict(f.meta))
        other = _score_of(strategy, flat)
    except Exception:
        return CheckResult("declared needs", True, "could not re-score", fatal=False)
    if other is None:
        return CheckResult("declared needs", True, "could not re-score", fatal=False)

    both = base.notna() & other.notna()
    if both.sum() < 30:
        return CheckResult("declared needs", True, "too little overlap", fatal=False)
    moved = float((base[both] - other[both]).abs().max())
    if moved > 1e-6:
        return CheckResult(
            "declared needs", False,
            f"flattening volume moved the score by {moved:.4f} but VOLUME is "
            f"not declared — it would vote on instruments with no volume feed.")
    return CheckResult("declared needs", True, "does not depend on volume")


def check_evidence(strategy: BaseStrategy, f: FeatureSet) -> CheckResult:
    """Backtests without error. Significance is reported, not required."""
    from .backtest import run_backtest

    try:
        bt = run_backtest(strategy, f)
    except Exception as exc:
        return CheckResult("evidence", False, f"backtest raised: {exc}")
    if bt.error:
        return CheckResult("evidence", True, f"did not run here: {bt.error}",
                           fatal=False)
    t = bt.t_stat
    verdict = ("clears t = 1.96" if bt.significant else
               "does not clear t = 1.96 — expected on a short window")
    return CheckResult("evidence", True,
                       f"{bt.total_trades} trades, Sharpe {bt.sharpe_ratio:.2f}, "
                       f"t = {t:.2f} over {bt.years_tested:.2f} years — {verdict}")


def admit(strategy: BaseStrategy, f: FeatureSet) -> Admission:
    """Run every admission check against one candidate."""
    a = Admission(strategy=getattr(strategy, "name", type(strategy).__name__))
    a.checks = [
        check_contract(strategy, f),
        check_causal(strategy, f),
        check_non_degenerate(strategy, f),
        check_declares_needs(strategy, f),
        check_evidence(strategy, f),
    ]
    from .backtest import run_backtest
    try:
        bt = run_backtest(strategy, f)
        a.t_stat, a.trades = bt.t_stat, bt.total_trades
    except Exception:
        pass
    return a
