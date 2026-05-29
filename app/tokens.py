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
    """Wraps ChatOpenAI to auto-track token usage on every invoke().

    Supports optional fallback provider: if the primary invoke() fails with
    a network/auth error, retries with the fallback LLM (if configured).
    """

    def __init__(self, llm: ChatOpenAI, node_name: str = "",
                 fallback_llm: ChatOpenAI | None = None) -> None:
        self._llm = llm
        self._fallback_llm = fallback_llm
        self._total_tokens: int = 0
        self._node_name = node_name
        self._used_fallback: bool = False

    def invoke(self, messages: list) -> Any:
        """Invoke LLM with fallback on network/auth errors."""
        response = self._try_invoke(messages, self._llm)
        if response is not None:
            return response
        if self._fallback_llm:
            logger = __import__("logging").getLogger(__name__)
            logger.warning(
                "Primary LLM failed, retrying with fallback provider "
                "(node: %s)", self._node_name or "unknown"
            )
            self._used_fallback = True
            response = self._try_invoke(messages, self._fallback_llm)
            if response is not None:
                return response
        raise RuntimeError(f"LLM call failed in node '{self._node_name}' — "
                           "no working provider (primary failed, no fallback configured). "
                           "Set FALLBACK_API_KEY/FALLBACK_API_BASE/FALLBACK_MODEL "
                           "or configure a local Ollama instance.")

    def _try_invoke(self, messages: list, llm: ChatOpenAI) -> Any:
        """Try invoke() on a specific LLM. Returns None on failure."""
        try:
            response = llm.invoke(messages)
            meta = getattr(response, "response_metadata", {}) or {}
            usage = meta.get("token_usage", {})
            self._total_tokens += usage.get("total_tokens", 0)
            return response
        except Exception:
            return None

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
    """Create a tracked ChatOpenAI instance with optional fallback provider.

    Args:
        node_name: Name of the calling node for per-node token breakdown
                  (e.g., 'planner', 'researcher', 'composer').
        fallback: If True, also configure fallback LLM from FALLBACK_* env vars.

    The returned wrapper auto-accumulates token usage on every .invoke() call.
    Call .token_delta() at the end of the node to get the state delta.
    On invoke() failure, automatically retries with fallback provider if configured.
    """
    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key or None,
        base_url=base_url or None,
        timeout=60,
        max_retries=2,
    )

    from app.config import config
    fallback_llm = None
    if config.fallback_api_key and config.fallback_api_base:
        fb_model = config.fallback_model or model
        fallback_llm = ChatOpenAI(
            model=fb_model,
            temperature=temperature,
            api_key=config.fallback_api_key,
            base_url=config.fallback_api_base,
            timeout=60,
            max_retries=2,
        )

    return _TrackedChatOpenAI(llm, node_name=node_name, fallback_llm=fallback_llm)
