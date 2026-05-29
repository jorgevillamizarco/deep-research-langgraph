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

    def __init__(self, llm: ChatOpenAI, node_name: str = "") -> None:
        self._llm = llm
        self._total_tokens: int = 0
        self._node_name = node_name

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
        last_meta = {}
        for chunk in self._llm.stream(messages):
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
        """Return state delta with accumulated tokens and per-node breakdown.

        Returns a dict with 'total_tokens' (int for operator.add) and
        'token_breakdown' (dict for operator.or_ merge).
        """
        delta: dict = {}
        if self._total_tokens:
            delta["total_tokens"] = self._total_tokens
            if self._node_name:
                delta["token_breakdown"] = {self._node_name: self._total_tokens}
        return delta


def get_llm(model: str, api_key: str | None = None, base_url: str | None = None,
            temperature: float = 0.2, node_name: str = "") -> _TrackedChatOpenAI:
    """Create a tracked ChatOpenAI instance. Standard factory for all nodes.

    Args:
        node_name: Name of the calling node for per-node token breakdown
                  (e.g., 'planner', 'researcher', 'composer').

    The returned wrapper auto-accumulates token usage on every .invoke() call.
    Call .token_delta() at the end of the node to get the state delta.
    """
    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key or None,
        base_url=base_url or None,
        timeout=60,
        max_retries=2,
    )
    return _TrackedChatOpenAI(llm, node_name=node_name)
