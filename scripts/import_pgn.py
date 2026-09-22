"""Phase 2: import a PGN file into the repertoire as approved lines.

Run with: python scripts/import_pgn.py <pgn_file> <repertoire_label> [db_path]
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from chess_trainer.db import DEFAULT_DB_PATH, get_connection  # noqa: E402
from chess_trainer.repertoire import import_pgn  # noqa: E402


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: python scripts/import_pgn.py <pgn_file> <repertoire_label> [db_path]")
        return 1
    pgn_path, repertoire = sys.argv[1], sys.argv[2]
    db_path = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("DB_PATH", str(DEFAULT_DB_PATH))

    pgn_text = Path(pgn_path).read_text()
    conn = get_connection(db_path)
    ids = import_pgn(conn, pgn_text, repertoire)
    conn.close()
    print(
        f"Imported {len(ids)} positions into repertoire '{repertoire}' "
        f"(root id {ids[0]}, leaf id {ids[-1]})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
