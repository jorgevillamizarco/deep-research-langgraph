"""Token tracking and shared LLM factory.

Usage in nodes:
    from app.tokens import get_llm
    llm = get_llm(model, api_key, base_url)
    response = llm.invoke(messages)
    return {"field": value, **get_llm.token_delta(response)}
"""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI


def get_llm(model: str, api_key: str | None = None, base_url: str | None = None,
            temperature: float = 0.2) -> ChatOpenAI:
    """Create a ChatOpenAI instance. Standard factory used by all nodes."""
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key or None,
        base_url=base_url or None,
    )


def get_llm_token_delta(response: Any) -> dict:
    """Extract token usage from an LLM response as a state delta.

    Returns {"total_tokens": N} for operator.add accumulation.
    """
    try:
        meta = getattr(response, "response_metadata", {}) or {}
        usage = meta.get("token_usage", {})
        total = usage.get("total_tokens", 0)
        if total:
            return {"total_tokens": total}
    except Exception:
        pass
    return {}
