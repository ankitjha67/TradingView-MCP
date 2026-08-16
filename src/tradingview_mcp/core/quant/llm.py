"""
Provider-agnostic LLM layer.

Save one API key and the whole pipeline runs — no Antigravity, no IDE, no
vendor SDK. Everything here uses ``urllib`` from the standard library, so there
is no dependency to install and nothing to break when a vendor SDK changes.
(The previous implementation imported ``litellm``, which was never installed,
so the entire LLM path raised ImportError on first use.)

Three wire formats cover every provider worth supporting:

* **OpenAI-compatible** ``/chat/completions`` — OpenAI, Groq, OpenRouter,
  Together, DeepSeek, xAI, Mistral, NVIDIA NIM, Perplexity, Fireworks, and every
  local server worth using (Ollama, LM Studio, vLLM, llama.cpp, LocalAI).
* **Anthropic Messages** ``/v1/messages``.
* **Google Gemini** ``generateContent``.

The LLM is strictly an explanation layer. It reads the numbers the quant engine
produced; it does not produce signals and cannot override them. That boundary is
deliberate — a language model asked to invent a price target will invent one.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / ".tradingview_mcp"
CONFIG_PATH = CONFIG_DIR / "llm_config.json"

OPENAI_STYLE = "openai"
ANTHROPIC_STYLE = "anthropic"
GEMINI_STYLE = "gemini"


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    style: str
    base_url: str
    default_model: str
    env_var: str = ""
    needs_key: bool = True
    models: tuple[str, ...] = ()
    notes: str = ""
    local: bool = False


# Model names change constantly. These are sensible defaults, not a hard list —
# the UI always allows typing any model string.
PROVIDERS: dict[str, Provider] = {
    "openai": Provider(
        "openai", "OpenAI", OPENAI_STYLE, "https://api.openai.com/v1",
        "gpt-4o-mini", "OPENAI_API_KEY",
        models=("gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o3-mini"),
        notes="Keys from platform.openai.com/api-keys"),
    "anthropic": Provider(
        "anthropic", "Anthropic (Claude)", ANTHROPIC_STYLE, "https://api.anthropic.com/v1",
        "claude-sonnet-4-5", "ANTHROPIC_API_KEY",
        models=("claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"),
        notes="Keys from console.anthropic.com"),
    "gemini": Provider(
        "gemini", "Google Gemini", GEMINI_STYLE,
        "https://generativelanguage.googleapis.com/v1beta",
        "gemini-2.0-flash", "GEMINI_API_KEY",
        models=("gemini-2.0-flash", "gemini-2.5-pro", "gemini-2.5-flash"),
        notes="Keys from aistudio.google.com/apikey — free tier available"),
    "nvidia": Provider(
        "nvidia", "NVIDIA NIM", OPENAI_STYLE, "https://integrate.api.nvidia.com/v1",
        "meta/llama-3.3-70b-instruct", "NVIDIA_API_KEY",
        models=("meta/llama-3.3-70b-instruct", "deepseek-ai/deepseek-r1",
                "qwen/qwen2.5-coder-32b-instruct"),
        notes="Free credits at build.nvidia.com"),
    "groq": Provider(
        "groq", "Groq", OPENAI_STYLE, "https://api.groq.com/openai/v1",
        "llama-3.3-70b-versatile", "GROQ_API_KEY",
        models=("llama-3.3-70b-versatile", "mixtral-8x7b-32768"),
        notes="Very fast inference; generous free tier at console.groq.com"),
    "openrouter": Provider(
        "openrouter", "OpenRouter", OPENAI_STYLE, "https://openrouter.ai/api/v1",
        "anthropic/claude-sonnet-4.5", "OPENROUTER_API_KEY",
        models=("anthropic/claude-sonnet-4.5", "openai/gpt-4o", "google/gemini-2.0-flash-001"),
        notes="One key for many vendors; some free models available"),
    "deepseek": Provider(
        "deepseek", "DeepSeek", OPENAI_STYLE, "https://api.deepseek.com/v1",
        "deepseek-chat", "DEEPSEEK_API_KEY", models=("deepseek-chat", "deepseek-reasoner")),
    "mistral": Provider(
        "mistral", "Mistral", OPENAI_STYLE, "https://api.mistral.ai/v1",
        "mistral-large-latest", "MISTRAL_API_KEY",
        models=("mistral-large-latest", "mistral-small-latest")),
    "together": Provider(
        "together", "Together AI", OPENAI_STYLE, "https://api.together.xyz/v1",
        "meta-llama/Llama-3.3-70B-Instruct-Turbo", "TOGETHER_API_KEY"),
    "xai": Provider(
        "xai", "xAI (Grok)", OPENAI_STYLE, "https://api.x.ai/v1",
        "grok-2-latest", "XAI_API_KEY"),
    "ollama": Provider(
        "ollama", "Ollama (local)", OPENAI_STYLE, "http://localhost:11434/v1",
        "llama3.2", "", needs_key=False, local=True,
        models=("llama3.2", "qwen2.5", "mistral", "phi4", "gemma2"),
        notes="Runs entirely on your machine. Install from ollama.com, then: ollama pull llama3.2"),
    "lmstudio": Provider(
        "lmstudio", "LM Studio (local)", OPENAI_STYLE, "http://localhost:1234/v1",
        "local-model", "", needs_key=False, local=True,
        notes="Start the local server from LM Studio's Developer tab"),
    "vllm": Provider(
        "vllm", "vLLM / llama.cpp (local)", OPENAI_STYLE, "http://localhost:8000/v1",
        "local-model", "", needs_key=False, local=True,
        notes="Any OpenAI-compatible local server"),
    "custom": Provider(
        "custom", "Custom OpenAI-compatible", OPENAI_STYLE, "", "",
        needs_key=False, notes="Point at any endpoint exposing /chat/completions"),
}


@dataclass
class LLMConfig:
    provider: str = "ollama"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.2
    max_tokens: int = 1200
    enabled: bool = False
    timeout: int = 90

    def resolved(self) -> tuple[Provider, str, str, str]:
        """Return (provider, model, base_url, api_key) with defaults and env applied."""
        p = PROVIDERS.get(self.provider, PROVIDERS["custom"])
        model = self.model or p.default_model
        base = (self.base_url or p.base_url).rstrip("/")
        key = self.api_key or (os.environ.get(p.env_var, "") if p.env_var else "")
        return p, model, base, key

    def to_dict(self, redact: bool = True) -> dict:
        d = dict(self.__dict__)
        if redact and d.get("api_key"):
            k = d["api_key"]
            d["api_key"] = f"{k[:4]}…{k[-4:]}" if len(k) > 12 else "…set…"
        return d


def load_config() -> LLMConfig:
    """Load saved config. Environment variables win over the saved file."""
    cfg = LLMConfig()
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
        except Exception:
            pass

    env_provider = os.environ.get("TVMCP_LLM_PROVIDER")
    if env_provider and env_provider in PROVIDERS:
        cfg.provider = env_provider
        cfg.enabled = True
    if os.environ.get("TVMCP_LLM_MODEL"):
        cfg.model = os.environ["TVMCP_LLM_MODEL"]

    # Adopt any provider key already present in the environment.
    if not cfg.api_key:
        p = PROVIDERS.get(cfg.provider)
        if p and p.env_var and os.environ.get(p.env_var):
            cfg.api_key = os.environ[p.env_var]
            cfg.enabled = True
    return cfg


def save_config(cfg: LLMConfig) -> Path:
    """
    Persist config to the user's home directory, readable only by them.

    Kept out of the project tree on purpose: an API key inside a git repository
    is one ``git add .`` away from being published.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg.__dict__, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except (OSError, NotImplementedError):
        pass  # Windows ACLs differ; the file is still under the user profile.
    return CONFIG_PATH


# ── transport ─────────────────────────────────────────────────────────────────

class LLMError(RuntimeError):
    pass


def _post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:600]
        raise LLMError(_explain_http(e.code, detail)) from None
    except urllib.error.URLError as e:
        raise LLMError(
            f"Could not reach {url}. {e.reason}. "
            "If this is a local provider, check the server is running."
        ) from None
    except TimeoutError:
        raise LLMError(f"Request to {url} timed out.") from None


def _explain_http(code: int, detail: str) -> str:
    """Turn a status code into something a non-expert can act on."""
    hints = {
        401: "Authentication failed — the API key is missing, wrong, or revoked.",
        403: "Access denied — the key is valid but not permitted to use this model.",
        404: "Not found — usually a wrong model name or base URL.",
        422: "The request was rejected — usually an unsupported model name.",
        429: "Rate limited or out of quota — wait, or check billing.",
        500: "The provider had a server error. Retry shortly.",
        503: "The provider is temporarily unavailable.",
    }
    return f"HTTP {code}: {hints.get(code, 'Request failed.')} Response: {detail}"


def _chat_openai(model, base, key, system, user, temp, max_tokens, timeout) -> str:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    data = _post(f"{base}/chat/completions", {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temp, "max_tokens": max_tokens,
    }, headers, timeout)
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LLMError(f"Unexpected response shape: {json.dumps(data)[:400]}") from None


def _chat_anthropic(model, base, key, system, user, temp, max_tokens, timeout) -> str:
    data = _post(f"{base}/messages", {
        "model": model, "system": system,
        "messages": [{"role": "user", "content": user}],
        "temperature": temp, "max_tokens": max_tokens,
    }, {"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout)
    try:
        return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
    except (KeyError, TypeError):
        raise LLMError(f"Unexpected response shape: {json.dumps(data)[:400]}") from None


def _chat_gemini(model, base, key, system, user, temp, max_tokens, timeout) -> str:
    url = f"{base}/models/{model}:generateContent?key={key}"
    data = _post(url, {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": temp, "maxOutputTokens": max_tokens},
    }, {}, timeout)
    try:
        return "".join(p.get("text", "")
                       for p in data["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        raise LLMError(f"Unexpected response shape: {json.dumps(data)[:400]}") from None


_DISPATCH = {OPENAI_STYLE: _chat_openai, ANTHROPIC_STYLE: _chat_anthropic,
             GEMINI_STYLE: _chat_gemini}


def chat(system: str, user: str, cfg: Optional[LLMConfig] = None) -> str:
    """Single completion against the configured provider."""
    cfg = cfg or load_config()
    p, model, base, key = cfg.resolved()

    if p.needs_key and not key:
        raise LLMError(
            f"No API key configured for {p.label}. "
            f"Set it in the dashboard's Settings page, or export {p.env_var}."
        )
    if not base:
        raise LLMError(f"No base URL configured for {p.label}.")
    if not model:
        raise LLMError(f"No model configured for {p.label}.")

    return _DISPATCH[p.style](model, base, key, system, user,
                              cfg.temperature, cfg.max_tokens, cfg.timeout)


def test_connection(cfg: Optional[LLMConfig] = None) -> dict:
    """Round-trip a trivial prompt so setup problems surface immediately."""
    cfg = cfg or load_config()
    p, model, base, key = cfg.resolved()
    started = time.time()
    try:
        reply = chat("You are a connection test. Reply with exactly: OK",
                     "Reply with exactly: OK", cfg)
        return {"ok": True, "provider": p.label, "model": model, "base_url": base,
                "latency_ms": int((time.time() - started) * 1000),
                "reply": reply.strip()[:120]}
    except LLMError as exc:
        return {"ok": False, "provider": p.label, "model": model, "base_url": base,
                "latency_ms": int((time.time() - started) * 1000), "error": str(exc)}


def list_local_models(cfg: Optional[LLMConfig] = None) -> list[str]:
    """Ask a local OpenAI-compatible server which models it currently has."""
    cfg = cfg or load_config()
    p, _, base, key = cfg.resolved()
    if not base:
        return []
    try:
        req = urllib.request.Request(
            f"{base}/models",
            headers={"Authorization": f"Bearer {key}"} if key else {})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return sorted(m.get("id", "") for m in data.get("data", []) if m.get("id"))
    except Exception:
        return []


# ── the analysis prompt ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a quantitative analyst reviewing the output of a systematic trading engine.

You are given the engine's computed results: a weighted consensus across hundreds of
published models, a regime classification, and per-category breakdowns. Your job is to
interpret these numbers — not to generate your own forecast.

Rules you must follow:
- Work only from the numbers provided. Never invent a price level, indicator value, or
  statistic that is not in the input.
- The consensus direction and score are the engine's output. Do not override them. If you
  think the reading is weak or contradictory, say so explicitly rather than substituting
  your own call.
- State the strongest argument against the consensus. A one-sided read is not analysis.
- Distinguish what the models measured from what they cannot see (news, positioning,
  liquidity, anything outside the price series).
- Be concise and concrete. No hedged filler, no motivational language.
- This is analysis of a model's output, not investment advice.

Structure your reply as:
1. **Read** — what the engine is saying, in two or three sentences.
2. **Support** — the specific model families and readings behind it.
3. **Against** — the strongest contrary evidence in the same data.
4. **Watch** — the concrete condition that would invalidate the read."""


def build_analysis_prompt(consensus: dict, risk: Optional[dict] = None,
                          extra: Optional[dict] = None) -> str:
    """Compose the user prompt from engine output only — no free-form narration."""
    parts = [
        f"SYMBOL: {consensus.get('symbol')}  INTERVAL: {consensus.get('interval')}",
        f"AS OF: {consensus.get('as_of')}",
        f"PRICE: {consensus.get('price')}",
        "",
        "ENGINE CONSENSUS",
        f"  direction: {consensus.get('direction')}",
        f"  score: {consensus.get('score')}  (-1 = max short, +1 = max long)",
        f"  confidence: {consensus.get('confidence')}",
        f"  agreement: {consensus.get('agreement')} of weight on the leading side",
    ]
    m = consensus.get("models", {})
    parts.append(f"  models: {m.get('voting')} voting of {m.get('available')} available "
                 f"({m.get('total')} in library) — {m.get('buy')} long / {m.get('sell')} short")

    reg = consensus.get("regime", {})
    if reg:
        parts += ["", "REGIME",
                  f"  classification: {reg.get('label')}",
                  f"  ADX: {reg.get('adx')}   trend strength: {reg.get('trend_strength')}",
                  f"  realized vol: {reg.get('realized_vol_pct')}%  (percentile {reg.get('vol_percentile')})",
                  f"  Hurst: {reg.get('hurst')}   efficiency ratio: {reg.get('efficiency_ratio')}",
                  f"  drawdown from peak: {reg.get('drawdown_pct')}%"]

    cats = consensus.get("categories", [])
    if cats:
        parts += ["", "BY CATEGORY (score, long/short votes, models available)"]
        for c in sorted(cats, key=lambda x: -abs(x.get("score", 0))):
            parts.append(f"  {c['category']}: {c['score']:+.2f}  "
                         f"{c['buy']}L/{c['sell']}S  ({c['available']}/{c['total']} available)")

    for label, key in (("STRONGEST LONG SIGNALS", "top_long"), ("STRONGEST SHORT SIGNALS", "top_short")):
        rows = consensus.get(key, [])
        if rows:
            parts += ["", label]
            for s in rows[:5]:
                parts.append(f"  [{s['score']:+.2f}] {s['strategy']} — {s['rationale']}")

    if risk:
        parts += ["", "RISK LEVELS (ATR-derived)",
                  f"  entry {risk.get('entry')}  stop {risk.get('stop_loss')}  "
                  f"target {risk.get('take_profit')}  R:R {risk.get('risk_reward')}"]

    unavail = consensus.get("unavailable_reasons", {})
    if unavail:
        parts += ["", "MODELS THAT COULD NOT RUN (and why)"]
        parts += [f"  {reason}: {count}" for reason, count in unavail.items()]

    if consensus.get("warnings"):
        parts += ["", "ENGINE WARNINGS"] + [f"  - {w}" for w in consensus["warnings"]]

    if extra:
        parts += ["", "ADDITIONAL CONTEXT", json.dumps(extra, indent=2, default=str)[:2000]]

    return "\n".join(parts)


def analyze(consensus: dict, risk: Optional[dict] = None,
            cfg: Optional[LLMConfig] = None, extra: Optional[dict] = None) -> dict:
    """
    Produce a narrative reading of the engine output.

    Returns a dict rather than raising, so a missing key degrades the dashboard
    to numbers-only instead of taking it down.
    """
    cfg = cfg or load_config()
    if not cfg.enabled:
        return {"ok": False, "skipped": True,
                "message": "LLM commentary is off. Enable it in Settings to add narrative analysis. "
                           "All signals, backtests and risk levels work without it."}
    try:
        text = chat(SYSTEM_PROMPT, build_analysis_prompt(consensus, risk, extra), cfg)
        p, model, _, _ = cfg.resolved()
        return {"ok": True, "provider": p.label, "model": model, "analysis": text}
    except LLMError as exc:
        return {"ok": False, "error": str(exc),
                "message": "Commentary unavailable — the numbers above are unaffected."}
