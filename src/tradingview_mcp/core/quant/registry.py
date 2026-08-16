"""
Strategy discovery and registry.

Auto-discovers every ``BaseStrategy`` subclass under ``core/quant/library`` and
exposes them through a single, canonically-imported registry.

The previous implementation had a subtle but serious defect: ``backtest_service``
imported ``src.tradingview_mcp...`` while everything else imported
``tradingview_mcp...``. Python treats those as two distinct packages, so the
module tree — and every strategy class in it — was loaded twice. ``BaseStrategy``
from one tree failed ``issubclass`` against the other, and the registry silently
held two non-interchangeable copies of every model. This module is the single
canonical import path; ``_canonical_root`` below refuses to be loaded under the
``src.`` prefix so the split cannot reappear.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
import threading
from typing import Iterable, Optional

from .base import BaseStrategy, DataNeed, Horizon, Regime

_LIBRARY_PACKAGE = "tradingview_mcp.core.quant.library"
_LEGACY_PACKAGE = "tradingview_mcp.core.services.strategies"


def _canonical_root() -> None:
    """Fail loudly if this module was reached via the duplicate ``src.`` path."""
    if __name__.startswith("src."):
        raise ImportError(
            "tradingview_mcp must be imported as 'tradingview_mcp.*', not 'src.tradingview_mcp.*'. "
            "Put the 'src' directory on sys.path instead of the project root."
        )


_canonical_root()


class StrategyRegistry:
    """
    Thread-safe singleton registry of all discovered models.

    Discovery is by class, keyed on ``name``. A duplicate name is a bug (two
    models claiming to be the same thing), so it is recorded in ``conflicts``
    and reported rather than silently overwriting.
    """

    _instance: Optional["StrategyRegistry"] = None
    _lock = threading.Lock()

    def __init__(self, packages: Iterable[str] = (_LIBRARY_PACKAGE,), strict: bool = False):
        self._strategies: dict[str, BaseStrategy] = {}
        self.conflicts: list[str] = []
        self.load_errors: list[str] = []
        self._packages = tuple(packages)
        self._strict = strict
        self.discover()

    # ── singleton access ──────────────────────────────────────────────────────
    @classmethod
    def instance(cls) -> "StrategyRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    # ── discovery ─────────────────────────────────────────────────────────────
    def discover(self) -> None:
        for pkg_name in self._packages:
            try:
                pkg = importlib.import_module(pkg_name)
            except ModuleNotFoundError:
                continue
            except Exception as exc:
                self.load_errors.append(f"{pkg_name}: {exc}")
                continue

            for _, mod_name, _ in pkgutil.iter_modules(pkg.__path__):
                if mod_name.startswith("_"):
                    continue
                self._load_module(f"{pkg_name}.{mod_name}")

    def _load_module(self, dotted: str) -> None:
        try:
            module = importlib.import_module(dotted)
        except Exception as exc:
            self.load_errors.append(f"{dotted}: {type(exc).__name__}: {exc}")
            if self._strict:
                raise
            return

        for _, obj in inspect.getmembers(module, inspect.isclass):
            # Only classes *defined here* — avoids re-registering imported symbols.
            if obj.__module__ != dotted:
                continue
            if not issubclass(obj, BaseStrategy) or obj is BaseStrategy:
                continue
            # Leading underscore marks an intermediate base (e.g. _ChainStrategy),
            # not a tradeable model. Same for anything still carrying the base name.
            if obj.__name__.startswith("_") or obj.name == BaseStrategy.name:
                continue
            if inspect.isabstract(obj) or getattr(obj, "abstract", False):
                continue
            try:
                inst = obj()
            except Exception as exc:
                self.load_errors.append(f"{dotted}.{obj.__name__}: init failed: {exc}")
                continue

            if inst.name in self._strategies:
                existing = type(self._strategies[inst.name]).__module__
                self.conflicts.append(
                    f"duplicate name {inst.name!r}: {existing}.{type(self._strategies[inst.name]).__name__}"
                    f" vs {dotted}.{obj.__name__}"
                )
                continue
            self._strategies[inst.name] = inst

    # ── query API ─────────────────────────────────────────────────────────────
    def all(self) -> list[BaseStrategy]:
        return list(self._strategies.values())

    def get(self, name: str) -> Optional[BaseStrategy]:
        return self._strategies.get(name)

    def names(self) -> list[str]:
        return sorted(self._strategies)

    def categories(self) -> list[str]:
        return sorted({s.category for s in self._strategies.values()})

    def families(self) -> list[str]:
        return sorted({s.family for s in self._strategies.values()})

    def by_category(self, category: str) -> list[BaseStrategy]:
        return [s for s in self._strategies.values() if s.category == category]

    def by_family(self, family: str) -> list[BaseStrategy]:
        return [s for s in self._strategies.values() if s.family == family]

    def filter(
        self,
        *,
        category: Optional[str] = None,
        family: Optional[str] = None,
        horizon: Optional[Horizon | str] = None,
        regime: Optional[Regime | str] = None,
        needs_only: Optional[Iterable[DataNeed | str]] = None,
        include_proxies: bool = True,
        max_bars: Optional[int] = None,
    ) -> list[BaseStrategy]:
        """Select models by metadata. ``needs_only`` keeps models whose entire
        requirement set is covered by the feeds you actually have."""
        out = self.all()
        if category:
            out = [s for s in out if s.category == category]
        if family:
            out = [s for s in out if s.family == family]
        if horizon:
            h = horizon.value if isinstance(horizon, Horizon) else str(horizon)
            out = [s for s in out if s.horizon.value == h]
        if regime:
            r = regime.value if isinstance(regime, Regime) else str(regime)
            out = [s for s in out if any(x.value in (r, "any") for x in s.regimes)]
        if needs_only is not None:
            have = {n.value if isinstance(n, DataNeed) else str(n) for n in needs_only}
            out = [s for s in out if {n.value for n in s.needs} <= have]
        if not include_proxies:
            out = [s for s in out if not s.is_proxy]
        if max_bars is not None:
            out = [s for s in out if s.min_bars <= max_bars]
        return out

    def specs(self) -> list[dict]:
        return [type(s).spec() for s in sorted(self._strategies.values(), key=lambda x: x.name)]

    def summary(self) -> dict:
        by_cat: dict[str, int] = {}
        for s in self._strategies.values():
            by_cat[s.category] = by_cat.get(s.category, 0) + 1
        return {
            "total": len(self._strategies),
            "categories": len(by_cat),
            "by_category": dict(sorted(by_cat.items())),
            "families": len(self.families()),
            "proxies": sum(1 for s in self._strategies.values() if s.is_proxy),
            "conflicts": self.conflicts,
            "load_errors": self.load_errors,
        }

    def __len__(self) -> int:
        return len(self._strategies)

    def __contains__(self, name: object) -> bool:
        return name in self._strategies


def get_registry() -> StrategyRegistry:
    return StrategyRegistry.instance()
