"""Create / reset schema from SQLAlchemy models.

Usage (from backend/):
  .\\.venv\\Scripts\\python -m scripts.init_db
  .\\.venv\\Scripts\\python -m scripts.init_db --drop
"""

from __future__ import annotations

import argparse

from app.core.db import get_engine
from app.models import Base


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize PostgreSQL schema")
    parser.add_argument("--drop", action="store_true", help="Drop all tables first (DEV ONLY)")
    args = parser.parse_args()

    engine = get_engine()
    if args.drop:
        Base.metadata.drop_all(bind=engine)
        print("dropped all tables")
    Base.metadata.create_all(bind=engine)
    print("create_all done:", sorted(Base.metadata.tables.keys()))


if __name__ == "__main__":
    main()
