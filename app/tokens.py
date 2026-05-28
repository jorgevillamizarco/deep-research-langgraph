"""Token tracking and shared LLM factory.

Usage in nodes:
    from app.tokens import get_llm

    llm = get_llm(model, api_key, base_url)
    response = llm.invoke(messages)  # tokens auto-tracked

    # At end of node, add token delta to return dict:
    return {"field": value, **llm.token_delta()}
"""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI


class _TrackedChatOpenAI:
    """Wraps ChatOpenAI to auto-track token usage on every invoke()."""

    def __init__(self, llm: ChatOpenAI) -> None:
        self._llm = llm
        self._total_tokens: int = 0

    def invoke(self, messages: list) -> Any:
        """Invoke LLM and accumulate token usage from response metadata."""
        response = self._llm.invoke(messages)
        try:
            meta = getattr(response, "response_metadata", {}) or {}
            usage = meta.get("token_usage", {})
            self._total_tokens += usage.get("total_tokens", 0)
        except Exception:
            pass
        return response

    def stream(self, messages: list):
        """Stream LLM output. Token tracking from final chunk metadata."""
        full_content = []
        last_meta = {}
        for chunk in self._llm.stream(messages):
            full_content.append(chunk.content if hasattr(chunk, "content") else str(chunk))
            try:
                meta = getattr(chunk, "response_metadata", {}) or {}
                if meta:
                    last_meta = meta
            except Exception:
                pass
            yield chunk
        # Track tokens from final chunk
        try:
            usage = last_meta.get("token_usage", {})
            self._total_tokens += usage.get("total_tokens", 0)
        except Exception:
            pass

    def token_delta(self) -> dict:
        """Return state delta with accumulated tokens for operator.add reducer."""
        if self._total_tokens:
            return {"total_tokens": self._total_tokens}
        return {}


def get_llm(model: str, api_key: str | None = None, base_url: str | None = None,
            temperature: float = 0.2) -> _TrackedChatOpenAI:
    """Create a tracked ChatOpenAI instance. Standard factory for all nodes.

    The returned wrapper auto-accumulates token usage on every .invoke() call.
    Call .token_delta() at the end of the node to get the state delta.
    """
    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key or None,
        base_url=base_url or None,
    )
    return _TrackedChatOpenAI(llm)
