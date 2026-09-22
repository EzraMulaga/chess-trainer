"""Phase 2: interactively approve or reject pending repertoire candidates.

Run with: python scripts/review_candidates.py [repertoire_label] [db_path]

For each pending position, shows the line leading to it and prompts
a(pprove) / r(eject) / s(kip).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from chess_trainer.db import DEFAULT_DB_PATH, get_connection  # noqa: E402
from chess_trainer.repertoire import line_to_root, list_pending, set_status  # noqa: E402


def _format_line(chain) -> str:
    parts = [row["move_san"] for row in chain if row["move_san"]]
    return " ".join(parts) or "(starting position)"


def main() -> int:
    repertoire = sys.argv[1] if len(sys.argv) > 1 else None
    db_path = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("DB_PATH", str(DEFAULT_DB_PATH))

    conn = get_connection(db_path)
    pending = list_pending(conn, repertoire)
    if not pending:
        print("No pending candidates.")
        return 0

    approved = rejected = skipped = 0
    for row in pending:
        chain = line_to_root(conn, row["id"])
        eval_str = ""
        if row["eval_mate"] is not None:
            eval_str = f" (mate in {row['eval_mate']})"
        elif row["eval_cp"] is not None:
            eval_str = f" ({row['eval_cp'] / 100:+.2f})"
        print(f"\n[{row['id']}] {_format_line(chain)}{eval_str}")
        choice = input("  (a)pprove / (r)eject / (s)kip? ").strip().lower()
        if choice == "a":
            set_status(conn, row["id"], "approved")
            approved += 1
        elif choice == "r":
            set_status(conn, row["id"], "rejected")
            rejected += 1
        else:
            skipped += 1

    conn.close()
    print(f"\nDone: {approved} approved, {rejected} rejected, {skipped} skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
