"""
Confidence engine.

Turns 311 model opinions into one score for a specific trade.

The premise: **model count is not evidence — independent agreement is.** Fifty
models from three families agreeing is weaker evidence than twenty models from
eighteen families agreeing, because the first is one idea restated. Every
component below is built around that distinction.

Eight components, each scored 0..1, combined into 0..100:

| Component | Weight | Question it answers |
|---|---|---|
| Conviction        | 18% | How strong is the weighted signal? |
| Agreement         | 18% | How one-sided is the weighted vote? |
| Family diversity  | 20% | How many *independent* ideas agree? |
| Concordance       | 14% | Do structurally opposed categories agree? |
| Regime alignment  | 12% | Are the agreeing models suited to these conditions? |
| Signal stability  | 08% | Is the read persistent or flickering bar to bar? |
| Data quality      | 06% | How much of the library could actually run? |
| Reward geometry   | 04% | Is the risk/reward worth taking? |

On top of that sit **hard vetoes** — conditions under which no score is high
enough to justify a trade. A confidence engine that cannot say "don't" is a
sales tool, not a risk tool.

Finally, ``calibrate()`` measures what confidence has *actually been worth* on
this instrument historically: forward returns and hit rates bucketed by score.
That is a measurement, not a claim. Where the sample is too thin to support a
conclusion, it says so instead of printing a number.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from .base import NEUTRAL_BAND, BaseStrategy, Regime, Signal
from .consensus import VOTE_BAND, ConsensusResult, _build_weights, _regime_fit
from .features import FeatureSet

# Categories that are structurally opposed. When members of an opposed pair agree,
# that is far stronger evidence than two trend models agreeing with each other.
OPPOSED_PAIRS = [
    ("Trend & Momentum", "Mean Reversion"),
    ("Trend & Momentum", "Statistical Arbitrage"),
    ("Volatility", "Trend & Momentum"),
    ("Microstructure", "Macro & Allocation"),
    ("Machine Learning", "Seasonality & Calendar"),
]

COMPONENT_WEIGHTS = {
    "conviction": 0.18,
    "agreement": 0.18,
    "family_diversity": 0.20,
    "concordance": 0.14,
    "regime_alignment": 0.12,
    "stability": 0.08,
    "data_quality": 0.06,
    "reward_geometry": 0.04,
}

GRADES = [(85, "A+"), (75, "A"), (65, "B"), (55, "C"), (45, "D"), (0, "F")]


@dataclass
class Component:
    name: str
    score: float          # 0..1
    weight: float
    detail: str
    raw: dict = field(default_factory=dict)

    @property
    def contribution(self) -> float:
        return self.score * self.weight * 100

    def to_dict(self) -> dict:
        return {"name": self.name, "score": round(self.score, 4),
                "weight": self.weight, "contribution": round(self.contribution, 2),
                "detail": self.detail, "raw": self.raw}


@dataclass
class ConfidenceReport:
    """A scored trade, with the full derivation kept so it can be argued with."""
    score: float                       # 0..100
    grade: str
    verdict: str                       # TRADE | REDUCED | STAND ASIDE
    direction: str
    size_multiplier: float             # 0..1 — feeds the sizing engine
    components: list[Component] = field(default_factory=list)
    vetoes: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)
    calibration: dict = field(default_factory=dict)

    @property
    def tradeable(self) -> bool:
        return self.verdict != "STAND ASIDE" and self.direction != "NEUTRAL"

    def to_dict(self) -> dict:
        return {"score": round(self.score, 2), "grade": self.grade,
                "verdict": self.verdict, "direction": self.direction,
                "size_multiplier": round(self.size_multiplier, 4),
                "tradeable": self.tradeable,
                "components": [c.to_dict() for c in self.components],
                "vetoes": self.vetoes, "cautions": self.cautions,
                "calibration": self.calibration}

    def summary_line(self) -> str:
        return (f"{self.grade} · {self.score:.0f}/100 · {self.verdict} · "
                f"size ×{self.size_multiplier:.2f}")


# ── components ────────────────────────────────────────────────────────────────

def _conviction(con: ConsensusResult) -> Component:
    s = min(1.0, abs(con.score) / 0.60)   # 0.60 weighted score = full marks
    return Component("Conviction", s, COMPONENT_WEIGHTS["conviction"],
                     f"Weighted consensus score {con.score:+.3f}.",
                     {"consensus_score": round(con.score, 4)})


def _agreement(con: ConsensusResult) -> Component:
    # 50% agreement is a coin flip and scores 0; 90% scores 1.
    s = float(np.clip((con.agreement - 0.50) / 0.40, 0, 1))
    return Component("Agreement", s, COMPONENT_WEIGHTS["agreement"],
                     f"{con.agreement:.0%} of weighted vote on the leading side "
                     f"({con.buy_votes} long / {con.sell_votes} short).",
                     {"agreement": round(con.agreement, 4)})


def _family_diversity(voting: list[tuple[BaseStrategy, Signal]], direction: str) -> Component:
    """
    The component that matters most.

    Counts distinct families on the winning side, not models. Twelve independent
    families is treated as full evidence; beyond that, added families are
    increasingly redundant, so the curve saturates.
    """
    want = 1 if direction == "BUY" else -1
    agreeing = {s.family for s, sig in voting if np.sign(sig.score) == want}
    opposing = {s.family for s, sig in voting if np.sign(sig.score) == -want}
    total = agreeing | opposing

    n = len(agreeing)
    breadth = 1 - math.exp(-n / 5.0)               # saturating: 5→0.63, 12→0.91
    purity = n / len(total) if total else 0.0      # share of ideas, not of models
    s = float(np.clip(0.65 * breadth + 0.35 * purity, 0, 1))

    return Component("Family diversity", s, COMPONENT_WEIGHTS["family_diversity"],
                     f"{n} independent families agree, {len(opposing)} disagree "
                     f"(from {len(voting)} voting models).",
                     {"agreeing_families": n, "opposing_families": len(opposing),
                      "voting_models": len(voting)})


def _concordance(con: ConsensusResult, direction: str) -> Component:
    """
    Do structurally opposed categories point the same way?

    Trend-following and mean-reversion are built on contradictory premises. When
    both lean the same direction it is unusually strong evidence; when they split
    it is the normal state and carries little information.
    """
    want = 1 if direction == "BUY" else -1
    by_cat = {c.category: c for c in con.categories if c.available > 0}

    aligned_cats = sum(1 for c in by_cat.values()
                       if abs(c.score) >= 0.10 and np.sign(c.score) == want)
    active_cats = sum(1 for c in by_cat.values() if abs(c.score) >= 0.10)
    base = aligned_cats / active_cats if active_cats else 0.0

    pairs_hit, pairs_checked = 0, 0
    for a, b in OPPOSED_PAIRS:
        ca, cb = by_cat.get(a), by_cat.get(b)
        if ca and cb and abs(ca.score) >= 0.10 and abs(cb.score) >= 0.10:
            pairs_checked += 1
            if np.sign(ca.score) == np.sign(cb.score) == want:
                pairs_hit += 1
    bonus = (pairs_hit / pairs_checked) if pairs_checked else 0.0

    s = float(np.clip(0.6 * base + 0.4 * bonus, 0, 1))
    detail = f"{aligned_cats} of {active_cats} active categories align."
    if pairs_checked:
        detail += f" {pairs_hit}/{pairs_checked} structurally opposed pairs agree."
    return Component("Concordance", s, COMPONENT_WEIGHTS["concordance"], detail,
                     {"aligned_categories": aligned_cats, "active_categories": active_cats,
                      "opposed_pairs_agreeing": pairs_hit, "opposed_pairs_checked": pairs_checked})


def _regime_alignment(voting: list[tuple[BaseStrategy, Signal]], f: FeatureSet,
                      direction: str) -> Component:
    """Are the models on the winning side ones designed for these conditions?"""
    want = 1 if direction == "BUY" else -1
    fits = [_regime_fit(s, f) for s, sig in voting if np.sign(sig.score) == want]
    if not fits:
        return Component("Regime alignment", 0.0, COMPONENT_WEIGHTS["regime_alignment"],
                         "No models on the leading side.", {})
    mean_fit = float(np.mean(fits))
    s = float(np.clip((mean_fit - 0.5) / 0.7, 0, 1))
    label = f.meta.get("regime_label", "")
    return Component("Regime alignment", s, COMPONENT_WEIGHTS["regime_alignment"],
                     f"Mean regime suitability {mean_fit:.2f} across agreeing models"
                     + (f" in a {label} tape." if label else "."),
                     {"mean_regime_fit": round(mean_fit, 3)})


def _stability(score_path: Optional[pd.Series], direction: str, bars: int = 10) -> Component:
    """
    Is the consensus persistent, or did it appear on this bar alone?

    A signal that has held for several bars is materially different from one that
    flipped on the latest close, and the difference is invisible in a snapshot.
    """
    if score_path is None or len(score_path.dropna()) < bars:
        return Component("Signal stability", 0.5, COMPONENT_WEIGHTS["stability"],
                         "Not enough history to assess persistence — scored neutral.", {})

    recent = score_path.dropna().tail(bars)
    want = 1 if direction == "BUY" else -1
    same_side = float((np.sign(recent) == want).mean())
    # Penalise a path that thrashes across zero even when it ends on the right side.
    flips = int((np.sign(recent).diff().fillna(0) != 0).sum())
    churn = 1 - min(1.0, flips / (bars / 2))
    s = float(np.clip(0.6 * same_side + 0.4 * churn, 0, 1))
    return Component("Signal stability", s, COMPONENT_WEIGHTS["stability"],
                     f"Consensus held this side on {same_side:.0%} of the last {bars} bars, "
                     f"{flips} direction change(s).",
                     {"same_side_fraction": round(same_side, 3), "flips": flips})


def _data_quality(con: ConsensusResult, f: FeatureSet,
                  voting: list[tuple[BaseStrategy, Signal]]) -> Component:
    coverage = con.models_available / con.models_total if con.models_total else 0.0
    participation = con.models_voting / con.models_available if con.models_available else 0.0
    proxy_share = (sum(1 for s, _ in voting if s.is_proxy) / len(voting)) if voting else 0.0
    depth = min(1.0, f.n / 500.0)

    s = float(np.clip(0.35 * coverage + 0.25 * participation + 0.25 * depth
                      + 0.15 * (1 - proxy_share), 0, 1))
    return Component("Data quality", s, COMPONENT_WEIGHTS["data_quality"],
                     f"{con.models_available}/{con.models_total} models runnable, "
                     f"{con.models_voting} voting, {f.n} bars, "
                     f"{proxy_share:.0%} of votes from proxy models.",
                     {"coverage": round(coverage, 3), "participation": round(participation, 3),
                      "proxy_share": round(proxy_share, 3), "bars": f.n})


# Realistic round-trip cost (both legs, commission + spread/slippage) as a % of
# notional. A signal whose target move does not clear this is unprofitable no
# matter how strong the consensus behind it.
ROUND_TRIP_COST_PCT = {
    "crypto": 0.20,     # ~0.10% per side on major spot venues
    "equity": 0.10,     # commission + spread on a liquid name
    "forex": 0.04,      # spread-only on a major pair
    "index": 0.10,
    "aggregate": 0.20,
}
# Target must clear costs by this multiple to be worth taking.
MIN_COST_MULTIPLE = 2.0


def _reward_geometry(risk_reward: float, natr_pct: float, target_move_pct: float,
                     cost_pct: float) -> Component:
    """
    Is the geometry worth trading *after costs*?

    The move the target implies must clear the round-trip cost by a healthy
    multiple. On fast intraday charts of low-priced instruments the ATR-derived
    target is routinely smaller than the fees, which makes the trade negative
    expectancy however strong the signal is.
    """
    rr = float(np.clip((risk_reward - 1.0) / 2.0, 0, 1)) if math.isfinite(risk_reward) else 0.0
    cost_multiple = (target_move_pct / cost_pct) if cost_pct > 0 else 0.0
    # Full marks at 4x costs; zero at or below 1x.
    cost_ok = float(np.clip((cost_multiple - 1.0) / 3.0, 0, 1))
    s = float(np.clip(0.45 * rr + 0.55 * cost_ok, 0, 1))
    return Component(
        "Reward geometry", s, COMPONENT_WEIGHTS["reward_geometry"],
        f"R:R {risk_reward:.2f}; target move {target_move_pct:.3f}% vs "
        f"{cost_pct:.2f}% round-trip cost ({cost_multiple:.2f}x).",
        {"risk_reward": round(risk_reward, 3), "natr_pct": round(natr_pct, 4),
         "target_move_pct": round(target_move_pct, 4), "cost_pct": cost_pct,
         "cost_multiple": round(cost_multiple, 3)})


# ── vetoes ────────────────────────────────────────────────────────────────────

def _collect_vetoes(con: ConsensusResult, f: FeatureSet, components: dict[str, Component],
                    risk_reward: float) -> tuple[list[str], list[str]]:
    """
    Hard blocks and soft cautions.

    A veto is a condition under which no component score should be allowed to
    produce a trade. These are deliberately blunt.
    """
    vetoes: list[str] = []
    cautions: list[str] = []

    if con.direction == "NEUTRAL":
        vetoes.append("Consensus is neutral — no directional edge to act on.")
    if con.agreement < 0.55:
        vetoes.append(f"Models are near-evenly split ({con.agreement:.0%} agreement) — "
                      "this is noise, not a signal.")

    fam = components["family_diversity"].raw.get("agreeing_families", 0)
    if fam < 4:
        vetoes.append(f"Only {fam} independent idea(s) agree — too narrow a base "
                      "regardless of how many models voted.")
    if con.models_voting < 15:
        vetoes.append(f"Only {con.models_voting} models produced a reading — insufficient sample.")
    if f.n < 120:
        vetoes.append(f"Only {f.n} bars of history — most models cannot warm up.")
    if math.isfinite(risk_reward) and risk_reward < 1.2:
        vetoes.append(f"Risk/reward {risk_reward:.2f} does not compensate for costs.")

    # The single most common way a strong-looking intraday signal loses money.
    geo = components["reward_geometry"].raw
    mult = geo.get("cost_multiple", float("inf"))
    if math.isfinite(mult) and mult < MIN_COST_MULTIPLE:
        vetoes.append(
            f"Target move is {geo.get('target_move_pct', 0):.3f}% against a "
            f"{geo.get('cost_pct', 0):.2f}% round-trip cost ({mult:.2f}x). "
            f"This trade is negative expectancy on fees alone, however strong the signal. "
            f"Use a slower interval or a more volatile instrument.")

    # Cautions do not block, but they scale size down.
    vol_pct = con.regime.get("vol_percentile", 0.5)
    if math.isfinite(vol_pct) and vol_pct > 0.90:
        cautions.append(f"Volatility is at the {vol_pct:.0%} percentile — stops are wide "
                        "and gap risk is elevated.")
    dd = con.regime.get("drawdown_pct", 0.0)
    if math.isfinite(dd) and dd < -25:
        cautions.append(f"Instrument is {dd:.0f}% below its peak — trend models are "
                        "unreliable in deep drawdowns (Daniel & Moskowitz 2016).")
    if components["data_quality"].raw.get("proxy_share", 0) > 0.4:
        cautions.append("Over 40% of the vote comes from proxy models approximating their "
                        "published method.")
    if con.models_available < con.models_total * 0.5:
        cautions.append(f"Only {con.models_available} of {con.models_total} models could run — "
                        "connect more data feeds for a broader read.")
    hurst = con.regime.get("hurst", 0.5)
    if math.isfinite(hurst) and 0.47 < hurst < 0.53:
        cautions.append(f"Hurst {hurst:.2f} — the series is close to a random walk here.")
    return vetoes, cautions


def _liquidity_check(f: FeatureSet, direction: str, notional_quote: float = 0.0,
                     asset_class: str = "equity") -> tuple[list[str], list[str]]:
    """
    Can this position actually be executed?

    A signal on an instrument nobody trades is not a trading opportunity. Two
    distinct failures, both invisible to a price-only model:

    * **Depth.** A position that is a meaningful share of daily turnover cannot
      be filled near the quoted price. The models see a clean price series
      because the last print was clean — not because size could transact there.
    * **Shortability.** Spot crypto and cash equity accounts can only sell what
      is owned. A SELL on an illiquid microcap is unborrowable in practice, so
      the signal is unactionable regardless of how strong it is.
    """
    vetoes: list[str] = []
    cautions: list[str] = []
    if not f.has_volume:
        return vetoes, cautions

    try:
        adv = float((f.close * f.volume).tail(30).mean())
    except Exception:
        return vetoes, cautions
    if not math.isfinite(adv) or adv <= 0:
        return vetoes, cautions

    # Absolute floor. Below this, quoted prices are not a real market.
    floor = {"crypto": 250_000.0, "equity": 1_000_000.0}.get(asset_class, 250_000.0)
    if adv < floor:
        vetoes.append(
            f"Average daily turnover is only ~{adv:,.0f} in quote currency — far below the "
            f"{floor:,.0f} needed for a quoted price to be executable. The models are reading "
            f"a price series that almost nothing trades at.")
        return vetoes, cautions

    # Participation: a position above ~1% of daily turnover moves the price against you.
    if notional_quote > 0:
        participation = notional_quote / adv
        if participation > 0.05:
            vetoes.append(
                f"Position would be {participation:.1%} of average daily turnover — "
                f"unfillable without moving the price against you.")
        elif participation > 0.01:
            cautions.append(
                f"Position is {participation:.1%} of average daily turnover; expect slippage "
                f"beyond the modelled cost.")

    if direction == "SELL" and asset_class == "crypto":
        cautions.append(
            "Short on spot crypto requires margin or a perpetual market. If the venue does "
            "not list this pair for margin, the signal is not actionable as a short.")
    return vetoes, cautions


def _calibration_check(cal: dict) -> tuple[list[str], list[str]]:
    """
    Fold the measured track record back into the decision.

    A score of 70 means nothing if, on this instrument, high scores have
    historically preceded *worse* outcomes than low ones. Calibration was
    previously computed and displayed but never allowed to affect the verdict,
    which left the engine unable to learn from its own measurement.
    """
    vetoes: list[str] = []
    cautions: list[str] = []
    if not cal or not cal.get("ok"):
        return vetoes, cautions

    spread = cal.get("spread") or {}
    edge = spread.get("hit_rate_edge_pts")
    if edge is None:
        return vetoes, cautions

    if edge <= -5.0:
        # Strongly inverse: strong signals have been actively worse than weak ones.
        vetoes.append(
            f"Calibration is inverted on this instrument and timeframe: the strongest "
            f"signals historically hit {spread['strongest_hit_rate_pct']:.1f}% versus "
            f"{spread['weakest_hit_rate_pct']:.1f}% for the weakest ({edge:+.1f} points). "
            f"Acting on a high score here has been worse than acting on a low one.")
    elif edge < 0:
        cautions.append(
            f"Calibration is weakly negative here ({edge:+.1f} points of hit rate between "
            f"strongest and weakest signals) — the score has not earned its keep on this "
            f"instrument.")
    return vetoes, cautions


# ── main entry point ──────────────────────────────────────────────────────────

def score_trade(
    con: ConsensusResult,
    f: FeatureSet,
    voting: Optional[Sequence[tuple[BaseStrategy, Signal]]] = None,
    *,
    risk_reward: float = 2.0,
    score_path: Optional[pd.Series] = None,
    calibration: Optional[dict] = None,
    target_move_pct: Optional[float] = None,
    asset_class: str = "equity",
    cost_pct: Optional[float] = None,
    notional_quote: float = 0.0,
) -> ConfidenceReport:
    """
    Score one prospective trade 0..100.

    ``voting`` is the (strategy, signal) list from ``evaluate_all``; without it,
    family diversity and regime alignment cannot be computed and are scored
    neutral rather than assumed good.

    ``target_move_pct`` is the distance to target as a percentage of price. It is
    checked against realistic round-trip costs for the asset class, because a
    target smaller than the fees is a losing trade regardless of signal strength.
    """
    voting = list(voting or [])
    direction = con.direction
    natr = con.regime.get("natr_pct", float("nan"))
    cost = cost_pct if cost_pct is not None else ROUND_TRIP_COST_PCT.get(asset_class, 0.10)
    # Default to the ATR-derived 3x target when the caller does not supply one.
    if target_move_pct is None:
        target_move_pct = natr * 3.0 if math.isfinite(natr) else float("nan")

    comps = {
        "conviction": _conviction(con),
        "agreement": _agreement(con),
        "family_diversity": _family_diversity(voting, direction) if voting else
            Component("Family diversity", 0.5, COMPONENT_WEIGHTS["family_diversity"],
                      "Per-model detail unavailable — scored neutral.", {"agreeing_families": 0}),
        "concordance": _concordance(con, direction),
        "regime_alignment": _regime_alignment(voting, f, direction) if voting else
            Component("Regime alignment", 0.5, COMPONENT_WEIGHTS["regime_alignment"],
                      "Per-model detail unavailable — scored neutral.", {}),
        "stability": _stability(score_path, direction),
        "data_quality": _data_quality(con, f, voting),
        "reward_geometry": _reward_geometry(risk_reward, natr, target_move_pct, cost),
    }

    raw_score = sum(c.contribution for c in comps.values())
    vetoes, cautions = _collect_vetoes(con, f, comps, risk_reward)

    # The engine's own measured track record on this instrument gets a vote.
    cal_vetoes, cal_cautions = _calibration_check(calibration or {})
    vetoes.extend(cal_vetoes)
    cautions.extend(cal_cautions)

    # Can the trade actually be executed at the size and in the direction implied?
    liq_vetoes, liq_cautions = _liquidity_check(f, direction, notional_quote, asset_class)
    vetoes.extend(liq_vetoes)
    cautions.extend(liq_cautions)

    # A veto caps the score rather than zeroing it, so the breakdown stays readable.
    score = min(raw_score, 35.0) if vetoes else raw_score
    score = float(np.clip(score, 0, 100))

    grade = next(g for threshold, g in GRADES if score >= threshold)

    if vetoes:
        verdict, mult = "STAND ASIDE", 0.0
    elif score >= 70:
        verdict, mult = "TRADE", 1.0
    elif score >= 55:
        verdict, mult = "TRADE", 0.65
    elif score >= 45:
        verdict, mult = "REDUCED", 0.35
    else:
        verdict, mult = "STAND ASIDE", 0.0

    # Each caution halves size, floored so a valid signal is never fully erased.
    if mult > 0 and cautions:
        mult = max(0.15, mult * (0.5 ** len(cautions)))

    return ConfidenceReport(
        score=score, grade=grade, verdict=verdict, direction=direction,
        size_multiplier=round(mult, 4),
        components=sorted(comps.values(), key=lambda c: -c.contribution),
        vetoes=vetoes, cautions=cautions, calibration=calibration or {})


# ── historical consensus & empirical calibration ──────────────────────────────

def consensus_series(f: FeatureSet, strategies: Sequence[BaseStrategy],
                     band: float = VOTE_BAND) -> pd.Series:
    """
    The weighted consensus score for **every bar**, not just the last one.

    Computed from the same family/category/proxy weights used live, so the
    historical path is the same quantity the engine reports today. This is what
    makes stability and calibration measurable rather than asserted.
    """
    paths: dict[str, pd.Series] = {}
    keep: list[BaseStrategy] = []
    for s in strategies:
        ok, _ = s.availability(f)
        if not ok:
            continue
        try:
            series = s.score_series(f)
        except Exception:
            continue
        if series.notna().sum() >= 10:
            paths[s.name] = series.where(series.abs() >= band, 0.0).fillna(0.0)
            keep.append(s)

    if not keep:
        return pd.Series(np.nan, index=f.close.index)

    # Reuse the live weighting (family split → regime fit → proxy discount → category norm).
    dummy = [(s, None) for s in keep]
    weights = _build_weights(dummy, f)  # type: ignore[arg-type]
    total = sum(weights.values()) or 1.0

    acc = pd.Series(0.0, index=f.close.index)
    for s in keep:
        acc = acc + paths[s.name] * weights[s.name]
    return acc / total


def calibrate(f: FeatureSet, strategies: Sequence[BaseStrategy],
              horizon: int = 10, min_samples: int = 25) -> dict:
    """
    Measure what consensus strength has actually been worth on this instrument.

    Buckets historical bars by |consensus score| and reports the mean forward
    return in the signalled direction, the hit rate, and the sample size.

    This is a measurement of the past on one instrument over one window. It is
    reported as such. Buckets thinner than ``min_samples`` are marked
    insufficient rather than given a misleading number.
    """
    path = consensus_series(f, strategies)
    if path.isna().all():
        return {"ok": False, "reason": "no consensus path could be computed"}

    fwd = f.close.pct_change(horizon).shift(-horizon)
    df = pd.DataFrame({"score": path, "fwd": fwd}).dropna()
    if len(df) < min_samples * 2:
        return {"ok": False, "reason": f"only {len(df)} usable bars; need {min_samples * 2}+"}

    # Return in the direction the signal pointed.
    df["directional"] = df["fwd"] * np.sign(df["score"])
    df["strength"] = df["score"].abs()

    # Quantile buckets, not fixed edges. Category-and-family normalisation compresses
    # the weighted score into a narrow band whose width differs by instrument and
    # interval, so fixed cut-points leave the top buckets empty and the comparison
    # untestable. Quintiles of the observed distribution always populate.
    try:
        df["q"] = pd.qcut(df["strength"], 5, labels=False, duplicates="drop")
    except ValueError:
        return {"ok": False, "reason": "consensus strength has too little variation to bucket"}

    n_buckets = int(df["q"].max()) + 1 if df["q"].notna().any() else 0
    if n_buckets < 3:
        return {"ok": False, "reason": "consensus strength has too little variation to bucket"}

    names = ["weakest 20%", "20-40%", "40-60%", "60-80%", "strongest 20%"][:n_buckets]
    buckets = []
    for q in range(n_buckets):
        rows = df[df["q"] == q]
        lo, hi = rows["strength"].min(), rows["strength"].max()
        label = f"{names[q]} (|score| {lo:.3f}–{hi:.3f})"
        n = len(rows)
        if n < min_samples:
            buckets.append({"bucket": label, "samples": n, "sufficient": False,
                            "note": f"only {n} samples — no conclusion drawn"})
            continue
        mean_ret = float(rows["directional"].mean())
        hit = float((rows["directional"] > 0).mean())
        buckets.append({
            "bucket": label, "samples": n, "sufficient": True,
            "mean_forward_return_pct": round(mean_ret * 100, 4),
            "hit_rate_pct": round(hit * 100, 2),
            "median_forward_return_pct": round(float(rows["directional"].median()) * 100, 4),
        })

    usable = [b for b in buckets if b.get("sufficient")]
    monotone = None
    spread = {}
    if len(usable) >= 3:
        rets = [b["mean_forward_return_pct"] for b in usable]
        hits = [b["hit_rate_pct"] for b in usable]
        # Two independent checks, because a 5-point correlation alone is noisy:
        #   1. does mean return rise with signal strength?
        #   2. does the strongest bucket actually beat the weakest?
        trend_ok = bool(np.corrcoef(range(len(rets)), rets)[0, 1] > 0.4)
        top_beats_bottom = bool(hits[-1] > hits[0] and rets[-1] > rets[0])
        monotone = trend_ok and top_beats_bottom
        spread = {
            "weakest_hit_rate_pct": hits[0], "strongest_hit_rate_pct": hits[-1],
            "hit_rate_edge_pts": round(hits[-1] - hits[0], 2),
            "weakest_return_pct": rets[0], "strongest_return_pct": rets[-1],
            "return_edge_pct": round(rets[-1] - rets[0], 4),
            "trend_correlation_ok": trend_ok, "top_beats_bottom": top_beats_bottom,
        }

    if monotone:
        verdict = (f"Consensus strength has tracked forward returns here: the strongest "
                   f"quintile hit {spread['strongest_hit_rate_pct']:.1f}% vs "
                   f"{spread['weakest_hit_rate_pct']:.1f}% for the weakest "
                   f"({spread['hit_rate_edge_pts']:+.1f} points).")
    elif monotone is False:
        verdict = (f"Consensus strength has NOT reliably tracked forward returns here "
                   f"(strongest quintile hit {spread.get('strongest_hit_rate_pct', 0):.1f}% "
                   f"vs {spread.get('weakest_hit_rate_pct', 0):.1f}% weakest). Treat the "
                   f"score as a measure of evidence quality, not of expected return, "
                   f"on this instrument and timeframe.")
    else:
        verdict = "Insufficient data across buckets to judge."

    return {
        "ok": True,
        "horizon_bars": horizon,
        "sample_bars": len(df),
        "buckets": buckets,
        "stronger_signal_paid_more": monotone,
        "spread": spread,
        "verdict": verdict,
        "caveat": ("Measured in-sample on one instrument over one window, with no "
                   "transaction costs. Not a forecast and not a win probability."),
    }
