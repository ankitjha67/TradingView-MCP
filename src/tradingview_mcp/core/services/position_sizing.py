import math

class PositionSizer:
    def __init__(self, min_capital_inr: float = 1000.0, max_capital_inr: float = 5000.0):
        self.min_capital = min_capital_inr
        self.max_capital = max_capital_inr
        # Approximate exchange rate: 1 USD = 83 INR (for crypto pairings which are typically in USD)
        self.usd_to_inr = 83.0
        
    def calculate_lot_size(self, current_price_usd: float, capital_inr: float, risk_per_trade: float = 1.0) -> float:
        """
        Calculate the precise lot size based on available capital in INR and the asset's current price in USD.
        :param current_price_usd: Current price of the asset (e.g., Bitcoin in USD)
        :param capital_inr: The capital available to deploy (must be between 1000 and 5000 INR)
        :param risk_per_trade: Fraction of the capital to use (0.0 to 1.0), defaults to 1.0 (full allocation)
        :return: fractional lot size (quantity) of the asset to buy
        """
        # Enforce capital bounds
        actual_capital = max(self.min_capital, min(capital_inr, self.max_capital))
        
        # Deployable capital in INR
        deployable_inr = actual_capital * risk_per_trade
        
        # Convert to USD
        deployable_usd = deployable_inr / self.usd_to_inr
        
        # Calculate quantity (fractional shares allowed for crypto)
        if current_price_usd <= 0:
            return 0.0
            
        quantity = deployable_usd / current_price_usd
        
        # Round to 6 decimal places for standard crypto exchange support
        return round(quantity, 6)

    def get_position_details(self, current_price_usd: float, capital_inr: float) -> dict:
        """
        Returns a dictionary containing lot size, total cost in USD, and total cost in INR.
        """
        qty = self.calculate_lot_size(current_price_usd, capital_inr)
        cost_usd = qty * current_price_usd
        cost_inr = cost_usd * self.usd_to_inr
        
        return {
            "quantity": qty,
            "cost_usd": round(cost_usd, 2),
            "cost_inr": round(cost_inr, 2),
            "max_allowed_inr": self.max_capital,
            "min_allowed_inr": self.min_capital
        }
