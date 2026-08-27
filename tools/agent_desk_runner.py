"""
Runs one TradingAgents debate and prints a single JSON object to stdout.

This file executes inside .venv-agents, NOT the project environment, and
imports nothing from tradingview_mcp. That separation is the entire point:
tradingagents requires pandas 3.x, chainlit, redis and some forty
opentelemetry packages, while the quant engine is 21 modules and 311 models on
pandas 2.3.3. One interpreter for both would upgrade pandas underneath the
library. The boundary is a JSON request on argv and a JSON reply on stdout.

Written against tradingagents 0.7.0, whose API differs from the README's
0.3.1 examples: configuration is a pydantic ``TradingAgentsConfig`` rather
than a ``DEFAULT_CONFIG`` dict, and ``propagate`` returns a structured
``TradeRecommendation`` rather than a decision string.

Called by src/tradingview_mcp/core/quant/agents.py; not useful standalone.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import time

# Report sections worth carrying back. The value of a second opinion is being
# able to read *why*, not just what, so these travel with the verdict.
REPORT_KEYS = (
    "market_report", "sentiment_report", "news_report", "fundamentals_report",
    "situation_summary", "investment_plan", "trader_investment_plan",
    "final_trade_decision",
)


def _reply(**kw) -> None:
    """Emit the single JSON object this process exists to produce."""
    sys.__stdout__.write(json.dumps(kw, default=str))
    sys.__stdout__.flush()


def _as_mapping(obj) -> dict:
    """
    Normalise a state object to a plain dict.

    AgentState is a pydantic BaseModel in 0.7.0, not the TypedDict the older
    docs imply, so `isinstance(obj, dict)` is False and a dict-only reader
    silently returns nothing. Handle both, and the nested debate states too —
    those are models as well.
    """
    if isinstance(obj, dict):
        return obj
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        try:
            return dump()
        except Exception:
            pass
    return dict(getattr(obj, "__dict__", {}) or {})


def _collect_reports(state) -> dict:
    data = _as_mapping(state)
    if not data:
        return {}
    out = {}
    for key in REPORT_KEYS:
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()
    for bucket in ("investment_debate_state", "risk_debate_state"):
        debate = _as_mapping(data.get(bucket))
        for side, val in debate.items():
            # `history` is the running transcript the other fields summarise.
            if isinstance(val, str) and val.strip() and side != "history":
                out[f"{bucket}.{side}"] = val.strip()
    return out


def main() -> int:
    try:
        req = json.loads(sys.argv[1]) if len(sys.argv) > 1 else json.load(sys.stdin)
    except Exception as exc:
        _reply(ok=False, error=f"bad request: {exc}")
        return 1

    ticker, day = req.get("ticker", ""), req.get("date", "")
    if not ticker or not day:
        _reply(ok=False, error="ticker and date are required")
        return 1

    for k, v in (req.get("env") or {}).items():
        if v:
            os.environ[k] = str(v)

    started = time.time()
    # The framework streams agent chatter to stdout, which would corrupt the
    # JSON reply, so stdout is captured for the duration and returned as a
    # separate field when something goes wrong.
    noise = io.StringIO()
    try:
        with contextlib.redirect_stdout(noise):
            from tradingagents.config import TradingAgentsConfig
            from tradingagents.graph import TradingAgentsGraph

            fields = {
                "llm_provider": req.get("llm_provider") or "openai",
                "deep_think_llm": req.get("deep_think_llm") or "gpt-4o-mini",
                "quick_think_llm": req.get("quick_think_llm") or "gpt-4o-mini",
                "max_debate_rounds": int(req.get("max_debate_rounds") or 1),
                "max_risk_discuss_rounds": int(req.get("max_risk_discuss_rounds") or 1),
                "max_recur_limit": int(req.get("max_recur_limit") or 100),
            }
            if req.get("reasoning_effort"):
                fields["reasoning_effort"] = req["reasoning_effort"]
            if req.get("results_dir"):
                fields["results_dir"] = req["results_dir"]

            cfg = TradingAgentsConfig(**fields)
            kwargs = {"config": cfg, "debug": False}
            if req.get("selected_analysts"):
                kwargs["selected_analysts"] = req["selected_analysts"]

            graph = TradingAgentsGraph(**kwargs)
            state, rec = graph.propagate(ticker, day)
    except ImportError as exc:
        _reply(ok=False, stage="import",
               error=f"tradingagents not importable: {exc}")
        return 1
    except Exception as exc:
        _reply(ok=False, stage="propagate",
               error=f"{type(exc).__name__}: {exc}",
               chatter=noise.getvalue()[-1500:],
               elapsed_s=round(time.time() - started, 1))
        return 1

    # TradeRecommendation is structured — signal is Literal['BUY','SELL','HOLD']
    # — so nothing here has to infer a direction from prose.
    rec_d = {}
    if rec is not None:
        dump = getattr(rec, "model_dump", None)
        rec_d = dump() if callable(dump) else dict(getattr(rec, "__dict__", {}))

    _reply(ok=True, ticker=ticker, date=day,
           recommendation=rec_d,
           reports=_collect_reports(state),
           elapsed_s=round(time.time() - started, 1),
           chatter=noise.getvalue()[-500:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
