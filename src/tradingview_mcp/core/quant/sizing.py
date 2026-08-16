"""
Capital allocation and position sizing.

Supports capital from **1,000 to 1,000,000** in the account currency. The
previous sizer hard-clamped every account to 1,000–5,000 INR, so any capital
above ₹5,000 was silently discarded before sizing.

Sizing is risk-first, not capital-first:

    risk budget   = capital × risk%
    scaled budget = risk budget × confidence multiplier
    raw quantity  = scaled budget ÷ (entry − stop)

Then constrained by instrument granularity (lot size, tick, minimum trade),
available capital, margin, and a maximum-exposure cap.

Sizing off the **stop distance** rather than the capital is what makes risk
constant across instruments: a wide-stop, high-volatility asset automatically
gets a smaller position than a tight-stop one for the same rupees at risk.

The confidence multiplier comes from ``confidence.py``. A score below its
threshold produces a multiplier of 0, and this module returns a plan with zero
quantity and a reason — it does not quietly fall back to a minimum position.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .market_data import SymbolSpec, parse_symbol

MIN_CAPITAL = 1_000.0
MAX_CAPITAL = 1_000_000.0

# Display ladder spanning the supported range, used for the sizing table.
CAPITAL_TIERS = (1_000, 5_000, 10_000, 25_000, 50_000,
                 100_000, 250_000, 500_000, 1_000_000)

DEFAULT_FX = {"INR": 1.0, "USD": 88.0, "EUR": 95.0, "GBP": 112.0}


@dataclass
class InstrumentSpec:
    """Trading constraints for one instrument."""
    asset_class: str
    units_label: str
    lot_size: float = 1.0          # contract multiplier; 1 for spot
    min_quantity: float = 1.0
    quantity_step: float = 1.0     # granularity
    max_leverage: float = 1.0
    fractional: bool = False
    quote_currency: str = "USD"
    note: str = ""
    # Minimum order VALUE the venue will accept, in the quote currency.
    #
    # Fractional instruments have an effectively unbounded minimum *quantity*
    # (0.000001 BTC is a valid number), so quantity alone cannot express what an
    # exchange will actually fill. Binance rejects any spot order under $5 of
    # notional regardless of how the quantity is expressed. Without this, a small
    # account gets handed an order it physically cannot place.
    min_notional: float = 0.0


# Indian index derivatives: exchange-mandated lot sizes.
_INDEX_LOTS = {"BANKNIFTY": 15.0, "NIFTY": 75.0, "FINNIFTY": 65.0, "SENSEX": 10.0}


def resolve_instrument(symbol: str, spec: Optional[SymbolSpec] = None) -> InstrumentSpec:
    """Derive tradeable constraints from the symbol."""
    spec = spec or parse_symbol(symbol)
    sym = (spec.ticker or symbol).upper()

    for name, lot in _INDEX_LOTS.items():
        if name in sym:
            return InstrumentSpec(
                asset_class=f"Index derivative ({name})", units_label="contracts",
                lot_size=lot, min_quantity=lot, quantity_step=lot, max_leverage=10.0,
                quote_currency="INR",
                note=f"Exchange lot size {lot:g}. Futures margin assumed ~10x notional.")

    if spec.asset_class == "crypto":
        return InstrumentSpec(
            asset_class="Cryptocurrency", units_label="coins", lot_size=1.0,
            min_quantity=1e-6, quantity_step=1e-6, max_leverage=1.0, fractional=True,
            quote_currency="USD", min_notional=5.0,
            note="Fractional to 6 decimals. Spot, unlevered. Venues reject orders "
                 "under about $5 of notional.")

    if spec.asset_class == "forex":
        return InstrumentSpec(
            asset_class="Forex", units_label="units", lot_size=100_000.0,
            min_quantity=1_000.0, quantity_step=1_000.0, max_leverage=30.0,
            quote_currency=sym[3:] if len(sym) >= 6 else "USD", min_notional=1_000.0,
            note="Micro lot = 1,000 units. Leverage capped at 30x per typical regulation.")

    if spec.asset_class == "index":
        return InstrumentSpec(
            asset_class="Index (cash)", units_label="units", fractional=True,
            quantity_step=0.01, min_quantity=0.01, quote_currency="INR" if
            sym.startswith(("NIFTY", "BANK", "SENSEX")) else "USD",
            note="Cash index — not directly tradeable; size shown for reference only.")

    quote = "INR" if spec.exchange in ("NSE", "BSE") else "USD"
    return InstrumentSpec(
        asset_class="Equity", units_label="shares", lot_size=1.0, min_quantity=1.0,
        quantity_step=1.0, max_leverage=1.0, quote_currency=quote,
        note="Whole shares, cash account.")


@dataclass
class CapitalConfig:
    """Account-level risk settings."""
    capital: float = 100_000.0
    currency: str = "INR"
    risk_pct: float = 1.0             # of capital, per trade
    max_position_pct: float = 25.0    # cap on notional as % of capital
    use_leverage: bool = False
    fx_rates: dict = field(default_factory=lambda: dict(DEFAULT_FX))

    def __post_init__(self):
        if not math.isfinite(self.capital):
            raise ValueError("capital must be a finite number")
        self.capital = float(min(max(self.capital, MIN_CAPITAL), MAX_CAPITAL))
        self.risk_pct = float(min(max(self.risk_pct, 0.05), 10.0))
        self.max_position_pct = float(min(max(self.max_position_pct, 1.0), 100.0))

    def rate_to_account(self, quote_currency: str) -> float:
        """Units of account currency per 1 unit of the instrument's quote currency."""
        if quote_currency == self.currency:
            return 1.0
        q = self.fx_rates.get(quote_currency, 1.0)
        a = self.fx_rates.get(self.currency, 1.0)
        return q / a if a else 1.0


@dataclass
class PositionPlan:
    """A concrete, executable position — or an explicit refusal to take one."""
    symbol: str
    direction: str
    asset_class: str
    units_label: str

    quantity: float
    lots: Optional[float]
    entry: float
    stop_loss: float
    take_profit: float

    notional_account_ccy: float
    capital_required: float
    leverage_used: float

    risk_amount: float
    risk_pct_of_capital: float
    reward_amount: float
    risk_reward: float
    return_on_capital_pct: float

    capital: float
    currency: str
    confidence_multiplier: float
    fx_rate: float

    tradeable: bool = True
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in self.__dict__.items()}
        return d

    def summary_line(self) -> str:
        if not self.tradeable:
            return f"No position — {'; '.join(self.reasons)}"
        return (f"{self.direction} {self.quantity:g} {self.units_label} "
                f"({self.currency} {self.capital_required:,.0f} deployed, "
                f"{self.currency} {self.risk_amount:,.0f} at risk = "
                f"{self.risk_pct_of_capital:.2f}% of capital)")


def _round_to_step(qty: float, step: float) -> float:
    if step <= 0:
        return qty
    return math.floor(qty / step) * step


def build_position(
    symbol: str,
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
    cfg: CapitalConfig,
    confidence_multiplier: float = 1.0,
    instrument: Optional[InstrumentSpec] = None,
) -> PositionPlan:
    """
    Size a position from the stop distance, scaled by confidence.

    Returns a plan with ``tradeable=False`` and a stated reason rather than a
    minimum-size fallback whenever the trade cannot be taken honestly.
    """
    spec = parse_symbol(symbol)
    inst = instrument or resolve_instrument(symbol, spec)
    fx = cfg.rate_to_account(inst.quote_currency)

    def refuse(reason: str) -> PositionPlan:
        return PositionPlan(
            symbol=symbol, direction=direction, asset_class=inst.asset_class,
            units_label=inst.units_label, quantity=0.0, lots=None,
            entry=entry, stop_loss=stop_loss, take_profit=take_profit,
            notional_account_ccy=0.0, capital_required=0.0, leverage_used=1.0,
            risk_amount=0.0, risk_pct_of_capital=0.0, reward_amount=0.0,
            risk_reward=0.0, return_on_capital_pct=0.0, capital=cfg.capital,
            currency=cfg.currency, confidence_multiplier=confidence_multiplier,
            fx_rate=fx, tradeable=False, reasons=[reason])

    if direction not in ("BUY", "SELL"):
        return refuse("No directional signal.")
    if confidence_multiplier <= 0:
        return refuse("Confidence engine returned a zero size multiplier — stand aside.")
    if not all(math.isfinite(x) and x > 0 for x in (entry, stop_loss, take_profit)):
        return refuse("Entry, stop or target is not a valid price.")

    risk_per_unit = abs(entry - stop_loss)
    if risk_per_unit <= 0:
        return refuse("Stop loss equals entry — risk per unit is zero.")

    reward_per_unit = abs(take_profit - entry)

    # Risk budget in account currency, scaled by confidence.
    risk_budget = cfg.capital * (cfg.risk_pct / 100.0) * confidence_multiplier
    # Convert the per-unit risk into account currency before dividing.
    risk_per_unit_acct = risk_per_unit * fx
    raw_qty = risk_budget / risk_per_unit_acct

    warnings: list[str] = []

    # ── constraint 1: instrument granularity ──
    qty = raw_qty if inst.fractional else _round_to_step(raw_qty, inst.quantity_step)
    if inst.fractional:
        qty = round(qty, 6)

    if qty < inst.min_quantity:
        # The account cannot take even one minimum unit within its risk budget.
        # Say precisely what would change that, rather than "increase capital".
        min_risk = inst.min_quantity * risk_per_unit_acct
        effective_pct = cfg.risk_pct * confidence_multiplier
        capital_needed = min_risk / (effective_pct / 100.0)
        risk_pct_needed = min_risk / cfg.capital * 100 / max(confidence_multiplier, 1e-9)

        fixes = []
        if capital_needed <= MAX_CAPITAL:
            fixes.append(f"capital of {cfg.currency} {capital_needed:,.0f}")
        if risk_pct_needed <= 10.0:
            fixes.append(f"risk of {risk_pct_needed:.2f}% per trade")
        fix_text = (" Tradeable at " + " or ".join(fixes) + "."
                    if fixes else
                    " Not reachable within the supported capital range at a sane risk level — "
                    "this instrument's lot size is too large for this account.")

        return refuse(
            f"One minimum position ({inst.min_quantity:g} {inst.units_label}) risks "
            f"{cfg.currency} {min_risk:,.0f} = {min_risk / cfg.capital * 100:.2f}% of "
            f"{cfg.currency} {cfg.capital:,.0f}, above the {effective_pct:.2f}% budget."
            + fix_text)

    # ── constraint 2: exposure cap ──
    leverage = inst.max_leverage if cfg.use_leverage else 1.0
    notional = qty * entry * fx
    max_notional = cfg.capital * (cfg.max_position_pct / 100.0) * leverage
    if notional > max_notional:
        capped = _round_to_step(max_notional / (entry * fx), inst.quantity_step) \
            if not inst.fractional else round(max_notional / (entry * fx), 6)
        if capped < inst.min_quantity:
            return refuse(
                f"Exposure cap of {cfg.max_position_pct:.0f}% of capital allows less than "
                f"the minimum tradeable size. Raise the cap or the capital.")
        warnings.append(
            f"Size reduced from {qty:g} to {capped:g} {inst.units_label} by the "
            f"{cfg.max_position_pct:.0f}% exposure cap.")
        qty = capped
        notional = qty * entry * fx

    # ── constraint 3: capital / margin ──
    capital_required = notional / leverage
    if capital_required > cfg.capital:
        affordable = (cfg.capital * leverage) / (entry * fx)
        capped = _round_to_step(affordable, inst.quantity_step) if not inst.fractional \
            else round(affordable, 6)
        if capped < inst.min_quantity:
            return refuse(
                f"{cfg.currency} {cfg.capital:,.0f} cannot fund the minimum "
                f"{inst.min_quantity:g} {inst.units_label} at {entry:,.4f}"
                + (f" even at {leverage:g}x leverage." if leverage > 1 else "."))
        warnings.append(
            f"Size reduced from {qty:g} to {capped:g} {inst.units_label} — capital limit.")
        qty = capped
        notional = qty * entry * fx
        capital_required = notional / leverage

    # ── constraint 4: venue minimum order value ──
    # Checked LAST, on the final quantity. The exposure cap and capital limit both
    # shrink the position, so a size that cleared the venue minimum before those
    # cuts can fall under it after — which is exactly the case for a small account,
    # where the 25% exposure cap is what binds. Checked in the instrument's quote
    # currency, since that is what the venue enforces.
    if inst.min_notional > 0 and (qty * entry) < inst.min_notional:
        order_value = qty * entry
        # What capital would make the minimum order fit inside the risk budget
        # *and* the exposure cap? Whichever binds harder is the real requirement.
        min_qty_needed = inst.min_notional / entry
        risk_at_min = min_qty_needed * risk_per_unit_acct
        effective_pct = max(cfg.risk_pct * confidence_multiplier, 1e-9)
        cap_for_risk = risk_at_min / (effective_pct / 100.0)
        cap_for_exposure = (inst.min_notional * fx) / (cfg.max_position_pct / 100.0) / leverage
        capital_needed = max(cap_for_risk, cap_for_exposure)

        binding = ("the exposure cap" if cap_for_exposure > cap_for_risk
                   else "the risk budget")
        fix = (f"Tradeable at {cfg.currency} {capital_needed:,.0f} capital "
               f"(currently limited by {binding})"
               if capital_needed <= MAX_CAPITAL else
               f"Not reachable within {cfg.currency} {MAX_CAPITAL:,.0f} at this risk level")
        return refuse(
            f"Final order value {inst.quote_currency} {order_value:,.2f} is below the "
            f"~{inst.quote_currency} {inst.min_notional:,.0f} minimum most venues accept — "
            f"the exchange would reject it. {fix}.")

    risk_amount = qty * risk_per_unit_acct
    reward_amount = qty * reward_per_unit * fx
    risk_pct_actual = risk_amount / cfg.capital * 100

    if risk_pct_actual > cfg.risk_pct * 1.5:
        warnings.append(
            f"Actual risk {risk_pct_actual:.2f}% exceeds the {cfg.risk_pct:.2f}% target "
            f"because lot granularity forced a larger position.")
    if leverage > 1:
        warnings.append(
            f"Assumes {leverage:g}x leverage. Losses scale with notional, not with margin.")

    lots = (qty / inst.lot_size) if inst.lot_size > 1 else None

    return PositionPlan(
        symbol=symbol, direction=direction, asset_class=inst.asset_class,
        units_label=inst.units_label, quantity=qty, lots=lots,
        entry=entry, stop_loss=stop_loss, take_profit=take_profit,
        notional_account_ccy=notional, capital_required=capital_required,
        leverage_used=leverage, risk_amount=risk_amount,
        risk_pct_of_capital=risk_pct_actual, reward_amount=reward_amount,
        risk_reward=reward_amount / risk_amount if risk_amount > 0 else 0.0,
        return_on_capital_pct=reward_amount / cfg.capital * 100,
        capital=cfg.capital, currency=cfg.currency,
        confidence_multiplier=confidence_multiplier, fx_rate=fx,
        tradeable=True, warnings=warnings)


def capital_ladder(
    symbol: str, direction: str, entry: float, stop_loss: float, take_profit: float,
    cfg: CapitalConfig, confidence_multiplier: float = 1.0,
    tiers: tuple = CAPITAL_TIERS,
) -> list[dict]:
    """
    Size the same trade across the full 1,000 → 1,000,000 ladder.

    Shows directly where an instrument becomes tradeable for a given account:
    a ₹1,000 account cannot take a Bank Nifty lot, and the table says so rather
    than printing an impossible number.
    """
    rows = []
    for tier in tiers:
        if tier < MIN_CAPITAL or tier > MAX_CAPITAL:
            continue
        tier_cfg = CapitalConfig(capital=float(tier), currency=cfg.currency,
                                 risk_pct=cfg.risk_pct,
                                 max_position_pct=cfg.max_position_pct,
                                 use_leverage=cfg.use_leverage, fx_rates=cfg.fx_rates)
        plan = build_position(symbol, direction, entry, stop_loss, take_profit,
                              tier_cfg, confidence_multiplier)
        rows.append({
            "capital": tier,
            "tradeable": plan.tradeable,
            "quantity": round(plan.quantity, 6) if plan.tradeable else 0,
            "lots": round(plan.lots, 2) if plan.tradeable and plan.lots else None,
            "capital_required": round(plan.capital_required, 2) if plan.tradeable else 0,
            "risk_amount": round(plan.risk_amount, 2) if plan.tradeable else 0,
            "risk_pct": round(plan.risk_pct_of_capital, 3) if plan.tradeable else 0,
            "reward_amount": round(plan.reward_amount, 2) if plan.tradeable else 0,
            "return_on_capital_pct": round(plan.return_on_capital_pct, 3) if plan.tradeable else 0,
            "note": ("; ".join(plan.warnings) if plan.tradeable
                     else "; ".join(plan.reasons)),
        })
    return rows


def build_trade_plan(
    symbol: str, consensus, risk_levels, confidence, cfg: CapitalConfig,
) -> dict:
    """
    Assemble the complete, auditable trade plan: signal → confidence → size.

    This is the single object the monitor, dashboard and MCP server all render,
    so every surface shows the same numbers derived the same way.
    """
    plan = build_position(
        symbol=symbol, direction=confidence.direction,
        entry=risk_levels.entry, stop_loss=risk_levels.stop_loss,
        take_profit=risk_levels.take_profit, cfg=cfg,
        confidence_multiplier=confidence.size_multiplier)

    ladder = capital_ladder(symbol, confidence.direction, risk_levels.entry,
                            risk_levels.stop_loss, risk_levels.take_profit,
                            cfg, confidence.size_multiplier) if confidence.tradeable else []

    return {
        "symbol": symbol,
        "signal": {"direction": consensus.direction, "score": round(consensus.score, 4),
                   "agreement": round(consensus.agreement, 4),
                   "models_voting": consensus.models_voting,
                   "models_available": consensus.models_available,
                   "models_total": consensus.models_total},
        "confidence": confidence.to_dict(),
        "levels": risk_levels.to_dict(),
        "position": plan.to_dict(),
        "capital_ladder": ladder,
        "account": {"capital": cfg.capital, "currency": cfg.currency,
                    "risk_pct": cfg.risk_pct, "max_position_pct": cfg.max_position_pct,
                    "use_leverage": cfg.use_leverage,
                    "supported_range": [MIN_CAPITAL, MAX_CAPITAL]},
    }
