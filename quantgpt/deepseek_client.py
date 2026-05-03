"""DeepSeek LLM — single entry point for OpenAI-compatible Chat Completions.

QuantGPT talks to DeepSeek via the official HTTPS API (`DEEPSEEK_BASE_URL`, default
`https://api.deepseek.com/v1`) using the `openai` Python SDK (`OpenAI` client).

Environment:
  DEEPSEEK_API_KEY   — required for factor NL generation / iteration / summaries
  DEEPSEEK_BASE_URL  — optional, defaults to DeepSeek API v1
  DEEPSEEK_MODEL     — optional, defaults to deepseek-v4-flash

Strategy codegen may override with STRATEGY_LLM_* (still defaults to same DeepSeek
credentials when unset); Anthropic is only used when STRATEGY_LLM_PROVIDER=anthropic
or the model name contains \"claude\".
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


def normalize_secret_env(value: str | None) -> str:
    """Strip BOM/whitespace and optional surrounding quotes (common .env mistakes)."""
    if value is None:
        return ""
    v = value.strip().lstrip("\ufeff")
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        v = v[1:-1]
    return v.strip()


def factor_llm_config() -> dict[str, str]:
    """Config for factor expressions, iteration, daily summary (DEEPSEEK_* only)."""
    return {
        "api_key": normalize_secret_env(os.environ.get("DEEPSEEK_API_KEY", "")),
        "base_url": os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL).rstrip("/"),
        "model": os.environ.get("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL).strip() or DEFAULT_DEEPSEEK_MODEL,
    }


def strategy_llm_config() -> dict[str, str]:
    """Config for strategy code generation; STRATEGY_LLM_* overrides DEEPSEEK_*."""
    key = normalize_secret_env(
        os.environ.get("STRATEGY_LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
    )
    base = (
        os.environ.get("STRATEGY_LLM_BASE_URL")
        or os.environ.get("DEEPSEEK_BASE_URL")
        or DEFAULT_DEEPSEEK_BASE_URL
    ).rstrip("/")
    model = (
        os.environ.get("STRATEGY_LLM_MODEL")
        or os.environ.get("DEEPSEEK_MODEL")
        or DEFAULT_DEEPSEEK_MODEL
    )
    provider = os.environ.get("STRATEGY_LLM_PROVIDER", "").lower()
    if not provider:
        provider = "anthropic" if "claude" in model.lower() else "openai"
    return {"api_key": key, "base_url": base, "model": model, "provider": provider}


def openai_sdk_client(*, api_key: str, base_url: str):
    """Return OpenAI SDK client pointed at DeepSeek (or any OpenAI-compatible endpoint)."""
    from openai import OpenAI

    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY environment variable is not set")
    return OpenAI(api_key=api_key, base_url=base_url.rstrip("/"))


def factor_llm_client():
    """Client for factor flows; raises if DEEPSEEK_API_KEY is missing."""
    cfg = factor_llm_config()
    return openai_sdk_client(api_key=cfg["api_key"], base_url=cfg["base_url"])


def chat_completion(
    client,
    *,
    model: str,
    messages: list[dict[str, Any]],
    **kwargs: Any,
):
    """Thin wrapper around `chat.completions.create` for typing and consistency."""
    return client.chat.completions.create(model=model, messages=messages, **kwargs)
