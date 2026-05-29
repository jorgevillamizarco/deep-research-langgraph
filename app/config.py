"""Configuration for the deep research agent.

Follows ADK's ResearchConfiguration pattern with dataclass + env var defaults.
"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ResearchConfig:
    """ADK-aligned configuration for model selection and research parameters.

    Attributes:
        worker_model: Model for generation/research tasks.
        critic_model: Model for evaluation tasks (can be a stronger model).
        max_search_iterations: Maximum critic→enhancer refinement cycles.
        worker_api_key: API key for the worker model provider.
        worker_api_base: Base URL for the worker model provider.
        critic_api_key: API key for the critic model provider (falls back to worker).
        critic_api_base: Base URL for the critic model provider (falls back to worker).
        output_dir: Directory for saving research reports.
        enable_evaluator: Whether to run the evaluator LLM (default: true).
    """

    worker_model: str = os.getenv("WORKER_MODEL", "deepseek-v4-flash")
    critic_model: str = os.getenv("CRITIC_MODEL", "deepseek-v4-pro")
    max_search_iterations: int = int(os.getenv("MAX_SEARCH_ITERATIONS", "5"))
    worker_api_key: str = os.getenv("WORKER_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    worker_api_base: str = os.getenv("WORKER_API_BASE", os.getenv("OPENAI_API_BASE", ""))
    critic_api_key: str = os.getenv("CRITIC_API_KEY", "")
    critic_api_base: str = os.getenv("CRITIC_API_BASE", "")
    output_dir: str = os.getenv("RESEARCH_OUTPUT_DIR", os.path.expanduser("~/research/agent-results"))
    enable_evaluator: bool = os.getenv("ENABLE_EVALUATOR", "true").lower() not in ("false", "0", "no", "")
    fallback_api_key: str = os.getenv("FALLBACK_API_KEY", "")
    fallback_api_base: str = os.getenv("FALLBACK_API_BASE", "")
    fallback_model: str = os.getenv("FALLBACK_MODEL", "")

    def validate(self) -> list[str]:
        """Validate configuration and return list of issues.

        Returns empty list if valid. Call at startup before any LLM operations.
        """
        issues: list[str] = []

        # Required: API key
        if not self.worker_api_key:
            issues.append(
                "WORKER_API_KEY is not set. Set it to your API key "
                "(e.g., export WORKER_API_KEY=sk-...). "
                "Without this, all LLM calls will fail."
            )

        # Required: API base URL
        if not self.worker_api_base:
            issues.append(
                "WORKER_API_BASE is not set. Set it to your API endpoint "
                "(e.g., export WORKER_API_BASE=https://api.deepseek.com). "
                "Without this, LLM requests won't know where to connect."
            )

        # Validation: max_iterations range
        if self.max_search_iterations < 1:
            issues.append(
                f"MAX_SEARCH_ITERATIONS={self.max_search_iterations} is too low. "
                "Must be at least 1. Using 1."
            )
        elif self.max_search_iterations > 10:
            issues.append(
                f"MAX_SEARCH_ITERATIONS={self.max_search_iterations} is high. "
                "Consider capping at 5-10 to avoid runaway API costs."
            )

        # Warning: critic same as worker
        effective_critic = self.critic_model or self.worker_model
        if effective_critic == self.worker_model:
            issues.append(
                f"CRITIC_MODEL ({effective_critic}) is the same as WORKER_MODEL "
                f"({self.worker_model}). Same-model evaluation inflates scores. "
                f"Set CRITIC_MODEL to a stronger model for honest quality checks."
            )

        return issues


config = ResearchConfig()
