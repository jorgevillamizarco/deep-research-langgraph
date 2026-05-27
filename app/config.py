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
    """

    worker_model: str = os.getenv("WORKER_MODEL", "deepseek-v4-flash")
    critic_model: str = os.getenv("CRITIC_MODEL", "deepseek-v4-flash")
    max_search_iterations: int = int(os.getenv("MAX_SEARCH_ITERATIONS", "5"))
    worker_api_key: str = os.getenv("WORKER_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    worker_api_base: str = os.getenv("WORKER_API_BASE", os.getenv("OPENAI_API_BASE", ""))
    critic_api_key: str = os.getenv("CRITIC_API_KEY", "")
    critic_api_base: str = os.getenv("CRITIC_API_BASE", "")
    output_dir: str = os.getenv("RESEARCH_OUTPUT_DIR", os.path.expanduser("~/research/agent-results"))


config = ResearchConfig()
