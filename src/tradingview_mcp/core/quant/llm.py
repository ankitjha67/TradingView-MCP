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
    model_notes: dict[str, str] = field(default_factory=dict)
    # Models the catalog advertises that cannot do general chat. Kept explicitly
    # so they are never offered — see NVIDIA_WRONG_MODALITY for why this matters.
    exclude: tuple[str, ...] = ()


# ── NVIDIA NIM, verified against a live key ───────────────────────────────────
#
# NVIDIA's /v1/models returns everything the key can address — embeddings,
# rerankers, OCR, safety classifiers, translation. Most of it answers HTTP 200
# to a /chat/completions call and then returns something useless. Probing with
# max_tokens=1 is therefore not enough to know a model is usable; every entry
# below was additionally given a real position-sizing question and had to get
# the answer right.
#
# What the probe found on 2026-08-17 (102 catalogued):
#   31 accepted a chat request
#   21 of those actually reasoned correctly
#    6 were the wrong modality entirely        <- NVIDIA_WRONG_MODALITY
#    2 answered but got the arithmetic wrong
#    2 were inconclusive (cold-start timeout)
#   71 rejected /chat/completions outright (embeddings, vision encoders, OCR)
#
# Of the 21, the 15 below are the current reasoning text models; the remaining
# six are older or vision-language and sit in NVIDIA_ALSO_WORKS.
#
# Re-run any time with: python tools/verify_llm_models.py --provider nvidia
# Ordered by a second measurement that matters more than raw latency: given the
# real SYSTEM_PROMPT, does the model return the four sections it was asked for,
# or does it return its own scratchpad? Counting characters cannot tell those
# apart — nemotron-3.5-lightning looked like the best model on length (3.8k
# characters, 7s) and is in fact unusable here: it emits `content` byte-identical
# to `reasoning_content`, spends the whole token budget thinking and never
# writes an answer. Timings below are wall-clock to a complete, structured reply.
NVIDIA_REASONING = (
    "nvidia/nemotron-3-nano-30b-a3b",                 # 2.3s — fastest clean answer
    "openai/gpt-oss-20b",                             # 5.3s
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",  # 6.0s
    "z-ai/glm-5.2",                                   # 7.4s
    "nvidia/nemotron-3-super-120b-a12b",              # 8.8s
    "nvidia/nvidia-nemotron-nano-9b-v2",              # 14.6s
    "nvidia/nemotron-3-ultra-550b-a55b",              # 48.0s — deepest, slow
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",       # 62.2s
    "meta/muse-glimmer-30b",                          # 100.2s
    "minimaxai/minimax-m3",                           # 114.8s, highly variable
)

# Reason correctly on a plain question but do not produce usable commentary at
# the default token budget, so they are not offered for it:
#
#   nemotron-3.5-lightning-30b-a3b  content == reasoning_content, finish=length
#   stepfun-ai/step-3.7-flash       content empty, finish=length
#   thinkingmachines/inkling        content empty, finish=length
#   google/gemma-4-31b-it           timed out past 150s on the full prompt
#   deepseek-ai/deepseek-v4-flash   timed out past 150s on the full prompt
#
# Plus superseded generations and two vision-language models. The VL ones are
# why this list is explicit rather than a looser filter: nemotron-nano-vl-8b-v1
# answered a sizing question correctly once and returned 27 instead of 277 on a
# re-run. A model that reasons only sometimes is worse here than one that fails
# loudly. All remain reachable through "Fetch models from API".
NVIDIA_ALSO_WORKS = (
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "stepfun-ai/step-3.7-flash",
    "thinkingmachines/inkling",
    "google/gemma-4-31b-it",
    "deepseek-ai/deepseek-v4-flash-0731",
    "nvidia/llama-3.3-nemotron-super-49b-v1",
    "meta/llama-3.1-70b-instruct",
    "meta/llama-3.1-8b-instruct",
    "google/diffusiongemma-26b-a4b-it",
    "nvidia/nemotron-nano-12b-v2-vl",
    "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
)

# Speed labels come from timing every model on the actual commentary prompt
# (~5,000 chars in, 1,200 tokens out). They are relative, not guarantees — NIM
# cold-starts an idle model, so a first call after a quiet spell costs more.
# This matters more than it looks: the dashboard's refresh is dominated by this
# call, not by the 311 models, which finish in about three seconds.
NVIDIA_MODEL_NOTES = {
    "nvidia/nemotron-3-nano-30b-a3b": "2s · fastest complete answer — default",
    "openai/gpt-oss-20b": "5s · GPT-OSS 20B, open weights",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": "6s · explicit reasoning",
    "z-ai/glm-5.2": "7s · GLM 5.2, most detailed of the fast ones",
    "nvidia/nemotron-3-super-120b-a12b": "9s · 120B MoE, stronger",
    "nvidia/nvidia-nemotron-nano-9b-v2": "15s · 9B, cheapest",
    "nvidia/nemotron-3-ultra-550b-a55b": "48s · 550B flagship, deepest — too slow for 1m",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5": "62s · reasoning-tuned 49B",
    "meta/muse-glimmer-30b": "100s · slow",
    "minimaxai/minimax-m3": "115s · very variable latency",
    # Not offered for commentary — see NVIDIA_ALSO_WORKS for why.
    "nvidia/nemotron-3.5-lightning-30b-a3b": "returns only its scratchpad",
    "stepfun-ai/step-3.7-flash": "returns empty at the default token budget",
    "thinkingmachines/inkling": "returns empty at the default token budget",
    "deepseek-ai/deepseek-v4-flash-0731": "times out on the full prompt",
    "google/gemma-4-31b-it": "times out on the full prompt",
    "nvidia/llama-3.3-nemotron-super-49b-v1": "superseded by v1.5",
    "meta/llama-3.1-70b-instruct": "previous generation",
    "meta/llama-3.1-8b-instruct": "previous generation · small",
    "google/diffusiongemma-26b-a4b-it": "diffusion LM · experimental",
    "nvidia/nemotron-nano-12b-v2-vl": "vision-language · handles text",
    "nvidia/llama-3.1-nemotron-nano-vl-8b-v1": "vision-language · handles text",
}

# These answer HTTP 200 and then return a safety verdict or a translation.
# Offering them in a model picker produces silent garbage, so they are blocked.
NVIDIA_WRONG_MODALITY = (
    "nvidia/llama-3.1-nemoguard-8b-content-safety",   # -> {"User Safety": "safe"}
    "nvidia/llama-3.1-nemoguard-8b-topic-control",    # -> "on-topic"
    "nvidia/llama-3.1-nemotron-safety-guard-8b-v3",   # -> {"User Safety": "safe"}
    "nvidia/nemotron-3.5-content-safety",             # -> "User Safety: safe"
    "nvidia/riva-translate-4b-instruct-v1.1",         # echoes the prompt back
    "nvidia/riva-translate-4b-instruct-v2",           # translated the prompt to Chinese
    "nvidia/nemotron-parse",                          # rejects plain-text input
    "nvidia/nemoretriever-parse",                     # rejects plain-text input
)


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
        # Default is the fastest model that returns a complete, correctly
        # structured answer — 2.3s against 48s for the 550B flagship, which
        # reasons better but is too slow to finish inside a 1-minute bar.
        "nvidia", "NVIDIA NIM", OPENAI_STYLE, "https://integrate.api.nvidia.com/v1",
        "nvidia/nemotron-3-nano-30b-a3b", "NVIDIA_API_KEY",
        models=NVIDIA_REASONING, model_notes=NVIDIA_MODEL_NOTES,
        exclude=NVIDIA_WRONG_MODALITY,
        notes="Free credits at build.nvidia.com. These 15 reasoning models were each "
              "verified against a live key by answering a real position-sizing "
              "question. Use “Fetch models from API” for the full catalog your key "
              "can reach, and “Verify all models” to re-test them."),
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
    # Reasoning models bill their private thinking against this budget before
    # writing a word of the answer. At 1200 the largest ones used the lot
    # thinking and returned an empty or one-line reply on the analysis prompt.
    max_tokens: int = 2400
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
        choice = data["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError):
        raise LLMError(f"Unexpected response shape: {json.dumps(data)[:400]}") from None

    text = (message.get("content") or "").strip()
    thinking = (message.get("reasoning_content") or "").strip()
    reason = choice.get("finish_reason")

    # Some models mirror their scratchpad into `content`. When the two fields
    # are identical the model never wrote an answer at all — it ran out of
    # budget mid-thought. Returning that would put "Here's a thinking process:
    # 1. Analyze the user's request" on the page as if it were the analysis.
    if text and thinking and text == thinking:
        raise LLMError(
            f"{model} returned only its reasoning trace — it used all "
            f"{max_tokens} tokens thinking and never wrote an answer. Raise "
            "'Max tokens' in Settings, or choose a model that answers directly.")
    if text:
        return text

    # Content empty but reasoning present: the thinking IS the substance here,
    # so show it rather than a blank panel.
    if thinking:
        return thinking

    if reason == "length":
        raise LLMError(
            f"{model} used its entire {max_tokens}-token budget before writing an "
            "answer. Raise 'Max tokens' in Settings, or pick a model that does not "
            "reason at length.")
    raise LLMError(f"{model} returned an empty response (finish_reason={reason!r}).")


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


def list_models(cfg: Optional[LLMConfig] = None, timeout: int = 20) -> list[str]:
    """
    Ask an OpenAI-compatible endpoint which models the key can address.

    Works for hosted providers as well as local servers. Note the catalog is a
    claim about addressability, not usability: NVIDIA lists embedding, OCR and
    safety models here that accept a chat request and return nonsense. Use
    ``verify_models`` when it matters which ones actually work.
    """
    cfg = cfg or load_config()
    p, _, base, key = cfg.resolved()
    if not base or p.style != OPENAI_STYLE:
        return []
    try:
        req = urllib.request.Request(
            f"{base}/models",
            headers={"Authorization": f"Bearer {key}"} if key else {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ids = {m.get("id", "") for m in data.get("data", []) if m.get("id")}
        return sorted(ids - set(p.exclude))
    except Exception:
        return []


# Backwards-compatible alias — the dashboard used to call this for local only.
list_local_models = list_models


# A question with one checkable answer, phrased the way the dashboard prompts.
# 2% of 50,000 = 1,000 risk budget; 180.00 - 176.40 = 3.60 per share;
# 1,000 / 3.60 = 277.7 -> 277 whole shares.
_PROBE_SYSTEM = "You are a quantitative analyst. Show your working, then give the final answer."
_PROBE_QUESTION = (
    "Capital is $50,000. The risk budget for this trade is 2% of capital.\n"
    "Entry price is $180.00 and the stop-loss is $176.40.\n\n"
    "Step 1: risk budget in dollars = 2% x 50000\n"
    "Step 2: risk per share = entry - stop\n"
    "Step 3: shares = step 1 / step 2, rounded DOWN to a whole number\n\n"
    "What is the answer to step 3?")
_PROBE_ANSWER = "277"


def verify_model(model: str, cfg: Optional[LLMConfig] = None,
                 timeout: int = 120) -> dict:
    """
    Decide whether one model can actually do this job.

    An HTTP 200 is not the test. A safety classifier returns 200 and the body
    ``{"User Safety": "safe"}``; a translation model returns 200 and the prompt
    rendered in Chinese. Both would sit in a model picker looking healthy. So
    the model has to answer a real question correctly to pass.
    """
    import re
    cfg = cfg or load_config()
    probe = LLMConfig(**{**cfg.__dict__, "model": model,
                         "max_tokens": 3000, "temperature": 0.0,
                         "timeout": timeout})
    started = time.time()
    try:
        reply = chat(_PROBE_SYSTEM, _PROBE_QUESTION, probe)
    except LLMError as exc:
        return {"model": model, "status": "error", "usable": False,
                "detail": str(exc)[:200], "ms": int((time.time() - started) * 1000)}

    text = (reply or "").strip()
    digits = re.findall(r"\d[\d,]*", text.replace(",", ""))
    correct = _PROBE_ANSWER in digits
    return {"model": model,
            "status": "ok" if correct else ("answered" if text else "empty"),
            "usable": correct, "reply": text[-160:],
            "ms": int((time.time() - started) * 1000)}


def verify_models(models: Optional[list[str]] = None,
                  cfg: Optional[LLMConfig] = None,
                  workers: int = 4,
                  progress=None) -> list[dict]:
    """
    Verify a list of models concurrently; returns one record each.

    ``progress`` is called with (done, total, record) after each result so a UI
    can show a bar. Defaults to the provider's declared model list.
    """
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock

    cfg = cfg or load_config()
    p, _, _, _ = cfg.resolved()
    models = models or list(p.models) or [p.default_model]
    lock, done = Lock(), [0]

    def one(m: str) -> dict:
        rec = verify_model(m, cfg)
        if progress:
            with lock:
                done[0] += 1
                progress(done[0], len(models), rec)
        return rec

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        return list(ex.map(one, models))


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
        # One labelled number per line, rounded. Packing two onto a line
        # ("ADX: 19.714808  trend strength: 0.297131") got the two transposed
        # in the reply — the model reported "ADX 0.28", quoting trend strength
        # under the ADX label. Eighteen significant digits invite the same
        # class of transcription error.
        def _n(key: str, dp: int = 2) -> str:
            v = reg.get(key)
            return f"{v:.{dp}f}" if isinstance(v, (int, float)) else str(v)

        parts += ["", "REGIME",
                  f"  classification: {reg.get('label')}",
                  f"  ADX: {_n('adx')}",
                  f"  trend strength: {_n('trend_strength')}",
                  f"  realized vol %: {_n('realized_vol_pct')}",
                  f"  realized vol percentile: {_n('vol_percentile')}",
                  f"  Hurst: {_n('hurst')}",
                  f"  efficiency ratio: {_n('efficiency_ratio')}",
                  f"  drawdown from peak %: {_n('drawdown_pct')}"]

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
