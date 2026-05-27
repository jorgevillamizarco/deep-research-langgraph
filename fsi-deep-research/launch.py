"""Launch the deep research agent with proper env var handling."""
from __future__ import annotations

import os
import sys

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env file manually (bypass shell redaction issues)
env_path = os.path.expanduser("~/.hermes/.env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if val and not key.startswith("#"):
                        os.environ.setdefault(key, val)

# Set our overrides
os.environ["WORKER_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "")
os.environ["WORKER_API_BASE"] = "https://api.deepseek.com"
os.environ["WORKER_MODEL"] = "deepseek-v4-flash"
os.environ["CRITIC_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "")
os.environ["CRITIC_API_BASE"] = "https://api.deepseek.com"
os.environ["CRITIC_MODEL"] = "deepseek-v4-flash"
os.environ["MAX_SEARCH_ITERATIONS"] = "3"

# Point output directly to the fsi-deep-research folder
os.environ["RESEARCH_OUTPUT_DIR"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
)

# Verify key loaded
ak = os.environ.get("WORKER_API_KEY", "")
if len(ak) > 8:
    print(f"API key loaded: {ak[:8]}...{ak[-4:]} ({len(ak)} chars)")
else:
    print("WARNING: No DEEPSEEK_API_KEY found!")
    sys.exit(1)

# Verify SearXNG is available
import httpx
try:
    r = httpx.get("http://localhost:8080/search?q=health&format=json", timeout=3.0)
    if r.status_code == 200:
        print("SearXNG: OK (http://localhost:8080)")
    else:
        print(f"SearXNG: unexpected status {r.status_code}")
except Exception as e:
    print(f"SearXNG: not available — {e}")
    print("Research will fall back to DuckDuckGo")

from app.cli import run_research

topic_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "research_topic.txt")
with open(topic_file) as f:
    topic = f.read()

run_research(topic, auto_approve=True)
