from typing import Dict, Any, Optional

def calculate_position_size(
    symbol: str,
    capital: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
    take_profit: float
) -> Dict[str, Any]:
    """
    Calculates the exact position size, lot size, margin required, and projected profits
    for a trade based on user's capital, risk tolerance, and asset class parameters.
    """
    symbol = symbol.upper().strip()
    
    # Check if we are in Option Buying mode for small accounts on Indian Index Derivatives
    is_option_buying = False
    if ("NIFTY" in symbol or "BANKNIFTY" in symbol) and capital <= 10000:
        is_option_buying = True
        asset_class = "Index Option (Buying)"
        lot_size = 15 if "BANKNIFTY" in symbol else 75
        units_label = "contracts"
        leverage = 1.0
        
        # Standard realistic weekly ATM/OTM option premium (₹60.0)
        entry_price = 60.0
        stop_loss = 42.0    # 30% Stop Loss
        take_profit = 96.0  # 60% Target (2:1 RR)
        risk_per_unit = entry_price - stop_loss
        
        # Adjust risk percent to 15% for micro accounts to make it viable
        actual_risk_pct = 15.0 if capital <= 5000 else risk_pct
        risk_amount = capital * (actual_risk_pct / 100.0)
        raw_position_size = risk_amount / risk_per_unit
    else:
        risk_amount = capital * (risk_pct / 100.0)
        risk_per_unit = abs(entry_price - stop_loss)
        
        if risk_per_unit == 0:
            return {"error": "Entry price and Stop Loss cannot be equal."}
            
        raw_position_size = risk_amount / risk_per_unit
        
        # Identify asset class and apply lot size constraints
        asset_class = "Equity/Spot"
        lot_size = 1
        min_size = 1.0
        units_label = "shares"
        leverage = 1.0
        
        # Indian Indices
        if "BANKNIFTY" in symbol:
            asset_class = "Index Derivative (Bank Nifty)"
            lot_size = 15
            min_size = 15.0
            units_label = "contracts"
            leverage = 10.0  # Approx leverage for futures
        elif "NIFTY" in symbol:
            asset_class = "Index Derivative (Nifty 50)"
            lot_size = 75
            min_size = 75.0
            units_label = "contracts"
            leverage = 10.0
        # Crypto
        elif any(crypto in symbol for crypto in ["BTC", "ETH", "SOL", "DOGE", "USDT"]):
            asset_class = "Cryptocurrency"
            lot_size = 1
            min_size = 0.0001
            units_label = "coins"
            leverage = 1.0
        # Forex
        elif len(symbol) == 6 or "USD" in symbol or "EUR" in symbol or "GBP" in symbol or "JPY" in symbol:
            asset_class = "Forex"
            lot_size = 100000  # Standard Lot
            min_size = 1000.0  # Micro Lot (0.01 lot)
            units_label = "units"
            leverage = 30.0    # Typical regulated leverage
        
    # Calculate execution sizes based on lot limits
    if is_option_buying:
        # Determine number of lots the capital can purchase
        max_lots_by_capital = int(capital // (lot_size * entry_price))
        recommended_lots = int(raw_position_size // lot_size)
        actual_lots = min(recommended_lots, max_lots_by_capital)
        if actual_lots == 0 and max_lots_by_capital >= 1:
            # force 1 lot if capital can buy it and user wants to trade
            actual_lots = 1
        actual_size = actual_lots * lot_size
        capital_required = actual_size * entry_price
    elif asset_class in ["Index Derivative (Bank Nifty)", "Index Derivative (Nifty 50)"]:
        number_of_lots = int(raw_position_size // lot_size)
        actual_size = number_of_lots * lot_size
        capital_required = (actual_size * entry_price) / leverage
    elif asset_class == "Cryptocurrency":
        actual_size = round(raw_position_size, 4)
        if actual_size < min_size:
            actual_size = 0.0
        capital_required = actual_size * entry_price
    elif asset_class == "Forex":
        micro_lots = int(raw_position_size // 1000)
        actual_size = micro_lots * 1000
        capital_required = (actual_size * entry_price) / leverage
    else:
        actual_size = int(raw_position_size)
        capital_required = actual_size * entry_price

    # Validate if capital required exceeds available capital
    if capital_required > capital:
        if is_option_buying:
            actual_lots = int(capital // (lot_size * entry_price))
            actual_size = actual_lots * lot_size
            capital_required = actual_size * entry_price
        elif asset_class in ["Index Derivative (Bank Nifty)", "Index Derivative (Nifty 50)"]:
            max_size_allowed = int((capital * leverage) // (entry_price * lot_size)) * lot_size
            actual_size = min(actual_size, max_size_allowed)
            capital_required = (actual_size * entry_price) / leverage
        elif asset_class == "Forex":
            max_size_allowed = int((capital * leverage) // (entry_price * 1000)) * 1000
            actual_size = min(actual_size, max_size_allowed)
            capital_required = (actual_size * entry_price) / leverage
        else:
            max_size_allowed = int(capital // entry_price)
            actual_size = min(actual_size, max_size_allowed)
            capital_required = actual_size * entry_price
        
    # Calculate exact profit & risk metrics
    actual_risk = actual_size * risk_per_unit
    potential_profit = actual_size * abs(take_profit - entry_price)
    rr_ratio = round(potential_profit / actual_risk, 2) if actual_risk > 0 else 0.0
    
    return {
        "symbol": symbol,
        "asset_class": asset_class,
        "capital_allocated": round(capital, 2),
        "target_risk_pct": 15.0 if is_option_buying and capital <= 5000 else risk_pct,
        "allowed_risk_amount": round(risk_amount, 2),
        "entry_price": round(entry_price, 4),
        "stop_loss": round(stop_loss, 4),
        "take_profit": round(take_profit, 4),
        "raw_size": round(raw_position_size, 4),
        "recommended_size": actual_size,
        "units_label": units_label,
        "lot_details": {
            "standard_lots": round(actual_size / 100000, 2) if asset_class == "Forex" else None,
            "mini_lots": round(actual_size / 10000, 2) if asset_class == "Forex" else None,
            "micro_lots": round(actual_size / 1000, 2) if asset_class == "Forex" else None,
            "contract_lots": int(actual_size // lot_size) if ("Derivative" in asset_class or "Option" in asset_class) else None
        },
        "capital_required": round(capital_required, 2),
        "leverage_used": leverage,
        "actual_risk_amount": round(actual_risk, 2),
        "projected_profit": round(potential_profit, 2),
        "risk_reward_ratio": rr_ratio,
        "return_on_capital_pct": round((potential_profit / capital) * 100, 2)
    }

