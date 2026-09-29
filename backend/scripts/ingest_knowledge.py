"""Ingest knowledge markdown into PostgreSQL + Milvus Lite/Server.

Usage (from backend/):
  .\\.venv\\Scripts\\python -m scripts.ingest_knowledge
  .\\.venv\\Scripts\\python -m scripts.ingest_knowledge --reset
"""

from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.models import Base
from app.core.db import get_engine
from app.rag.ingest import ingest_knowledge_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest knowledge base")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate vector collection")
    parser.add_argument("--dir", type=str, default="", help="Override knowledge directory")
    args = parser.parse_args()

    # ensure tables exist
    Base.metadata.create_all(bind=get_engine())

    get_settings.cache_clear()
    result = ingest_knowledge_dir(args.dir or None, reset_vectors=args.reset)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
