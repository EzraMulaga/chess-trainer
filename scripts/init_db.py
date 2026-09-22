"""Phase 1: initialize the SQLite schema.

Run with: python scripts/init_db.py [path/to/db]
Defaults to data/chess_trainer.db (gitignored).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from chess_trainer.db import DEFAULT_DB_PATH, get_connection, init_db  # noqa: E402


def main() -> int:
    db_path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DB_PATH", str(DEFAULT_DB_PATH))
    conn = get_connection(db_path)
    init_db(conn)
    conn.close()
    print(f"Initialized schema at {db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
