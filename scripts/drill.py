"""Phase 3: SRS drill loop.

Run with: python scripts/drill.py [repertoire_label] [db_path]

Shows the board before each due move, accepts a SAN or UCI guess, grades
recall (correct guesses ask for a quality of 3-5, wrong guesses auto-grade
0), and updates the SM-2 schedule.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from chess_trainer.db import DEFAULT_DB_PATH, get_connection  # noqa: E402
from chess_trainer.srs import (  # noqa: E402
    board_before_move,
    check_answer,
    get_due_positions,
    grade_review,
    sync_srs_state,
)


def main() -> int:
    repertoire = sys.argv[1] if len(sys.argv) > 1 else None
    db_path = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("DB_PATH", str(DEFAULT_DB_PATH))

    conn = get_connection(db_path)
    created = sync_srs_state(conn, repertoire)
    if created:
        print(f"Initialized SRS tracking for {created} newly approved position(s).")

    due = get_due_positions(conn, repertoire)
    if not due:
        print("Nothing due right now.")
        return 0

    print(f"{len(due)} position(s) due.\n")
    correct_count = 0
    for row in due:
        board = board_before_move(conn, row)
        print(board)
        side = "White" if board.turn else "Black"
        user_input = input(f"({side} to move) Your move? ").strip()

        correct = check_answer(board, row["move_uci"], user_input)
        if correct:
            print("Correct!")
            correct_count += 1
            quality_input = input("Quality [3=hard, 4=good, 5=easy] (default 4): ").strip()
            quality = int(quality_input) if quality_input else 4
            quality = max(3, min(5, quality))
        else:
            print(f"Incorrect. Correct move was {row['move_san']}.")
            quality = 0

        result = grade_review(conn, row["id"], quality, correct)
        print(f"  next due in {result.interval_days} day(s)\n")

    conn.close()
    print(f"Session complete: {correct_count}/{len(due)} correct.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
