"""Runtime configuration for the Retrieval Arena API.

Everything is environment-driven so the same image runs locally and on Railway.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Where the built indexes live. Railway containers are ephemeral, which is fine:
# the whole corpus is small enough to rebuild on every boot.
BUILD_DIR = Path(os.getenv("BUILD_DIR", "/tmp/retrieval-arena"))
SQLITE_PATH = BUILD_DIR / "arena.db"
KUZU_PATH = BUILD_DIR / "graph"

# --- Claude planner -------------------------------------------------------
# The planner turns natural language into SQL / Cypher / an embedding string.
# Default is the most capable model; drop to claude-sonnet-5 or claude-haiku-4-5
# via PLANNER_MODEL if you want a cheaper public demo.
PLANNER_MODEL = os.getenv("PLANNER_MODEL", "claude-opus-5")
PLANNER_EFFORT = os.getenv("PLANNER_EFFORT", "low")
PLANNER_MAX_TOKENS = int(os.getenv("PLANNER_MAX_TOKENS", "4000"))
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# --- Embeddings -----------------------------------------------------------
# Local ONNX model via fastembed. No API key, no per-query cost.
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_DIM = int(os.getenv("EMBED_DIM", "384"))

# --- Serving --------------------------------------------------------------
PORT = int(os.getenv("PORT", "8000"))
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,https://localhost:3000",
    ).split(",")
    if o.strip()
]
# Vercel preview deployments get a new subdomain per push, so allow the pattern too.
CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX", r"https://.*\.vercel\.app")

# --- Guardrails for a public demo ----------------------------------------
MAX_QUERY_CHARS = int(os.getenv("MAX_QUERY_CHARS", "300"))
DEFAULT_LIMIT = int(os.getenv("DEFAULT_LIMIT", "8"))
MAX_LIMIT = int(os.getenv("MAX_LIMIT", "25"))
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))
PLAN_CACHE_SIZE = int(os.getenv("PLAN_CACHE_SIZE", "512"))
