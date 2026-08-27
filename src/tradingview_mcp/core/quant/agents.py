"""
TradingAgents desk — an independent second opinion, deliberately not a vote.

TauricResearch/TradingAgents runs a team of LLM agents (fundamentals, news,
sentiment and technical analysts, then bull/bear researchers, a trader and a
risk manager) who debate their way to a BUY/SELL/HOLD. That is the opposite of
this engine's rule, stated at the top of llm.py: the LLM explains what the
models found and cannot originate or override a signal.

Both can hold at once, so the desk is wired as a *second opinion*:

  * It never sets direction. ``compute_consensus`` is untouched.
  * It never sizes. ``build_trade_plan`` never sees it.
  * When it contradicts the quant consensus it adds a caution, which halves
    position size (floored at 0.15) — it can shrink a trade, never create one.
  * When it agrees it says so and changes nothing.

Why bother: every run reports roughly 119 of 311 models standing down for
"missing data feed" — options chains, fundamentals, on-chain, news, sentiment.
Those are precisely the inputs TradingAgents has. It is not a better price
model; it sees a different part of the problem.

Two practical constraints shape the rest of this module.

*Isolation.* tradingagents requires pandas 3.x, chainlit, redis and some forty
opentelemetry packages. This engine is 21 modules and 311 models on pandas
2.3.3. One interpreter for both would upgrade pandas underneath the library,
so the desk lives in its own virtualenv (.venv-agents) and is reached over a
subprocess with JSON on the wire.

*Cost.* A debate is many LLM calls over minutes, and this engine re-analyses
at every bar close, 1-minute bars included. So a verdict is cached per
(ticker, trading date): news and fundamentals do not move between two minutes,
and that is what the debate is reading.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date as _date
from pathlib import Path
from typing import Optional

CACHE_DIR = Path.home() / ".tradingview_mcp" / "agent_desk"
VENV_DIR_NAME = ".venv-agents"

# A debate is minutes of work, not seconds. Past this something has hung, and
# the quant pipeline must not wait on it.
RUN_TIMEOUT_SECONDS = 900

BUY_WORDS = ("buy", "long", "bullish", "accumulate", "overweight")
SELL_WORDS = ("sell", "short", "bearish", "reduce", "underweight")


def _project_root() -> Path:
    # .../src/tradingview_mcp/core/quant/agents.py -> project root
    return Path(__file__).resolve().parents[4]


def venv_python() -> Path:
    root = _project_root() / VENV_DIR_NAME
    return root / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def runner_script() -> Path:
    return _project_root() / "tools" / "agent_desk_runner.py"


@dataclass
class AgentVerdict:
    """
    One desk verdict. ``available`` False means it did not run, and why.

    ``size_fraction``, ``target`` and ``stop`` are carried for display only.
    Nothing in this engine sizes from them — position sizing stays with
    ``build_trade_plan`` and the confidence engine, which are calibrated
    against measured history the desk does not have.
    """
    available: bool = False
    reason_unavailable: str = ""
    ticker: str = ""
    as_of: str = ""
    direction: str = "NEUTRAL"      # BUY | SELL | NEUTRAL (HOLD maps to NEUTRAL)
    confidence: float = 0.0         # the desk's own 0..1, not this engine's grade
    size_fraction: float = 0.0      # advisory only — never fed to the sizer
    target: Optional[float] = None
    stop: Optional[float] = None
    horizon_days: Optional[int] = None
    rationale: str = ""
    warning: str = ""
    decision_text: str = ""
    reports: dict = field(default_factory=dict)
    elapsed_s: float = 0.0
    cached: bool = False
    error: str = ""

    def agrees_with(self, quant_direction: str) -> Optional[bool]:
        """True/False agreement, or None when either side has no opinion."""
        if not self.available or self.direction == "NEUTRAL":
            return None
        if quant_direction not in ("BUY", "SELL"):
            return None
        return self.direction == quant_direction

    def to_dict(self) -> dict:
        d = asdict(self)
        d["decision_text"] = self.decision_text[:2000]
        d["rationale"] = self.rationale[:2000]
        d["reports"] = {k: v[:4000] for k, v in self.reports.items()}
        return d


def parse_direction(text: str) -> str:
    """
    Read BUY / SELL / HOLD out of the desk's closing verdict.

    The decision is prose and the agents argue both sides at length, so
    counting keywords over the whole text would mostly measure how much the
    bear said. Only the closing lines are the verdict, and an explicit
    "FINAL TRANSACTION PROPOSAL: **BUY**" wins outright when present.
    """
    if not text:
        return "NEUTRAL"
    low = text.lower()

    marker = "final transaction proposal"
    if marker in low:
        tail = low.split(marker, 1)[1][:120]
        if any(w in tail for w in BUY_WORDS):
            return "BUY"
        if any(w in tail for w in SELL_WORDS):
            return "SELL"
        if "hold" in tail:
            return "NEUTRAL"

    tail = "\n".join(low.strip().splitlines()[-6:])
    buy = any(w in tail for w in BUY_WORDS)
    sell = any(w in tail for w in SELL_WORDS)
    if buy and not sell:
        return "BUY"
    if sell and not buy:
        return "SELL"
    return "NEUTRAL"


def availability() -> tuple[bool, str]:
    """Can the desk run right now? Returns (ok, reason_if_not)."""
    exe = venv_python()
    if not exe.exists():
        return False, ("agent desk not installed — no interpreter at "
                       f"{exe}. Run: python tools/setup_agent_desk.py")
    if not runner_script().exists():
        return False, f"agent desk runner missing at {runner_script()}"
    return True, ""


def _cache_path(ticker: str, day: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in ticker)
    return CACHE_DIR / f"{safe}_{day}.json"


def load_cached(ticker: str, day: str) -> Optional[AgentVerdict]:
    p = _cache_path(ticker, day)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None          # a corrupt cache entry is a miss, not a failure
    allowed = set(AgentVerdict().__dict__)
    verdict = AgentVerdict(**{k: v for k, v in data.items() if k in allowed})
    verdict.cached = True
    return verdict


def run_desk(ticker: str, day: Optional[str] = None, *,
             llm_provider: str = "", model: str = "", backend_url: str = "",
             api_key: str = "", debate_rounds: int = 1,
             refresh: bool = False,
             timeout: int = RUN_TIMEOUT_SECONDS) -> AgentVerdict:
    """
    Return today's desk verdict for ``ticker``, debating only if needed.

    Cached per (ticker, day) because that is the resolution the inputs really
    have. A debate per 1-minute bar would be hundreds of LLM calls an hour to
    re-read the same morning's news.
    """
    day = day or _date.today().isoformat()

    if not refresh:
        hit = load_cached(ticker, day)
        if hit is not None:
            return hit

    ok, why = availability()
    if not ok:
        return AgentVerdict(available=False, reason_unavailable=why,
                            ticker=ticker, as_of=day)

    req: dict = {"ticker": ticker, "date": day,
                 "max_debate_rounds": debate_rounds, "env": {}}
    if llm_provider:
        req["llm_provider"] = llm_provider
    if model:
        req["deep_think_llm"] = model
        req["quick_think_llm"] = model
    if backend_url:
        req["backend_url"] = backend_url
    # tradingagents reads OpenAI-compatible credentials from the environment.
    # Passed to the child process only — never written to the cache on disk.
    env: dict = {}
    if api_key:
        env["OPENAI_API_KEY"] = api_key
    if backend_url:
        # An OpenAI-compatible endpoint that is not OpenAI (NVIDIA NIM, Groq,
        # a local vLLM) is reached by pointing the base URL at it and leaving
        # llm_provider as "openai" — langchain-openai honours both variables.
        env["OPENAI_BASE_URL"] = backend_url
        env["OPENAI_API_BASE"] = backend_url
    req["env"] = env

    started = time.time()
    try:
        proc = subprocess.run(
            [str(venv_python()), str(runner_script()), json.dumps(req)],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(_project_root()))
    except subprocess.TimeoutExpired:
        return AgentVerdict(available=False, ticker=ticker, as_of=day,
                            reason_unavailable=f"debate exceeded {timeout}s",
                            elapsed_s=round(time.time() - started, 1))
    except OSError as exc:
        return AgentVerdict(available=False, ticker=ticker, as_of=day,
                            reason_unavailable=f"could not start the desk: {exc}")

    raw = (proc.stdout or "").strip()
    if not raw:
        return AgentVerdict(available=False, ticker=ticker, as_of=day,
                            reason_unavailable="the desk produced no output",
                            error=(proc.stderr or "")[-600:])
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return AgentVerdict(available=False, ticker=ticker, as_of=day,
                            reason_unavailable="the desk returned unparseable output",
                            error=raw[-600:])

    if not data.get("ok"):
        return AgentVerdict(available=False, ticker=ticker, as_of=day,
                            reason_unavailable=data.get("error", "unknown failure"),
                            error=(data.get("chatter") or "")[-600:],
                            elapsed_s=float(data.get("elapsed_s") or 0))

    reports = data.get("reports") or {}
    rec = data.get("recommendation") or {}

    # 0.7.0 returns a structured TradeRecommendation whose `signal` is already
    # Literal['BUY','SELL','HOLD'], so trust it. parse_direction is the
    # fallback for an older build, or one that returned prose only.
    signal = str(rec.get("signal") or "").upper()
    if signal in ("BUY", "SELL"):
        direction = signal
    elif signal == "HOLD":
        direction = "NEUTRAL"
    else:
        direction = parse_direction(reports.get("final_trade_decision", ""))

    def _f(key) -> Optional[float]:
        v = rec.get(key)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    verdict = AgentVerdict(
        available=True, ticker=ticker, as_of=day, direction=direction,
        confidence=_f("confidence") or 0.0,
        size_fraction=_f("size_fraction") or 0.0,
        target=_f("target_price"), stop=_f("stop_loss"),
        horizon_days=(int(rec["time_horizon_days"])
                      if rec.get("time_horizon_days") is not None else None),
        rationale=str(rec.get("rationale") or ""),
        warning=str(rec.get("warning_message") or ""),
        decision_text=reports.get("final_trade_decision", ""),
        reports=reports,
        elapsed_s=float(data.get("elapsed_s") or 0), cached=False)

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(ticker, day).write_text(
            json.dumps(verdict.to_dict(), indent=1), encoding="utf-8")
    except OSError:
        pass          # a cold cache is a cost problem, not a correctness one
    return verdict


def desk_params_from_llm_config(cfg=None) -> dict:
    """
    Reuse the provider already configured in Settings, so the desk needs no
    second key.

    tradingagents names only eight providers and NVIDIA NIM is not among them,
    but NIM speaks the OpenAI wire format — as do Groq, Together, Fireworks,
    vLLM and LM Studio. All of them are reached as provider "openai" with the
    base URL pointed elsewhere, which is the same assumption llm.py already
    makes for its own OPENAI_STYLE transport.
    """
    from .llm import PROVIDERS, load_config

    cfg = cfg or load_config()
    provider, model, base, key = cfg.resolved()
    native = {"openai", "anthropic", "google_genai", "xai", "openrouter", "ollama"}
    name = {"gemini": "google_genai"}.get(provider.key, provider.key)

    if name in native and provider.key != "nvidia":
        return {"llm_provider": name, "model": model,
                "backend_url": base if provider.key != "openai" else "",
                "api_key": key}
    return {"llm_provider": "openai", "model": model,
            "backend_url": base, "api_key": key}


def concordance_caution(verdict: AgentVerdict,
                        quant_direction: str) -> Optional[str]:
    """
    The one channel through which the desk may affect a trade.

    A caution halves position size (floored at 0.15 in ``score_trade``). There
    is deliberately no path here that raises a score, sets a direction, or
    vetoes: the desk is a second reader, and a second reader who disagrees is a
    reason to take less, not a reason to trade the other way.
    """
    agrees = verdict.agrees_with(quant_direction)
    if agrees is None or agrees:
        return None
    return (f"The agent desk read this as {verdict.direction} against the models' "
            f"{quant_direction}, working from news, fundamentals and sentiment the "
            f"price models cannot see. Size halved; direction unchanged.")
