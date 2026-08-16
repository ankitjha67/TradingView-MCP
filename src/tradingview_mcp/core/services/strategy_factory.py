import importlib
import pkgutil
import inspect
import sys
from typing import Dict, Type, List, Any
import numpy as np
import pandas as pd

class BaseStrategy:
    """Base class for all 200+ quantitative strategies."""
    name = "BaseStrategy"
    category = "General"
    
    def __init__(self):
        pass
        
    def evaluate(self, df: pd.DataFrame) -> str:
        """Returns BUY, SELL, or NEUTRAL"""
        return "NEUTRAL"
        
class StrategyFactory:
    """Dynamically loads and instantiates all 200+ hedge-fund strategies."""
    
    def __init__(self):
        self.strategies: Dict[str, BaseStrategy] = {}
        self._load_all_strategies()
        
    def _load_all_strategies(self):
        # We will dynamically import modules from the strategies package
        import src.tradingview_mcp.core.services.strategies as strategies_pkg
        
        for _, module_name, _ in pkgutil.iter_modules(strategies_pkg.__path__):
            full_module_name = f"src.tradingview_mcp.core.services.strategies.{module_name}"
            module = importlib.import_module(full_module_name)
            
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
                    strategy_instance = obj()
                    self.strategies[strategy_instance.name] = strategy_instance
                    
    def get_all_strategies(self) -> List[BaseStrategy]:
        return list(self.strategies.values())
