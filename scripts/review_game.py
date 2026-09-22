"""Phase 4: review a full game — per-move Stockfish eval and classification.

Run with:
  python scripts/review_game.py <pgn_file> [--stockfish PATH] \
      [--search-depth N] [--db PATH]
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from chess_trainer.db import DEFAULT_DB_PATH, get_connection  # noqa: E402
from chess_trainer.review import ReviewConfig, review_game  # noqa: E402


def _format_eval(cp, mate) -> str:
    if mate is not None:
        return f"#{mate}"
    if cp is None:
        return "?"
    return f"{cp / 100:+.2f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pgn_file")
    parser.add_argument(
        "--stockfish",
        default=None,
        help="path to stockfish binary (default: $STOCKFISH_PATH, then PATH lookup)",
    )
    parser.add_argument("--search-depth", type=int, default=16)
    parser.add_argument("--db", default=os.environ.get("DB_PATH", str(DEFAULT_DB_PATH)))
    args = parser.parse_args()

    engine_path = args.stockfish or os.environ.get("STOCKFISH_PATH") or shutil.which("stockfish")
    if not engine_path:
        print("Stockfish not found on PATH; pass --stockfish /path/to/stockfish")
        return 1

    pgn_text = Path(args.pgn_file).read_text()
    config = ReviewConfig(search_depth=args.search_depth)

    conn = get_connection(args.db)
    game_id, reviews = review_game(conn, engine_path, pgn_text, config)
    conn.close()

    print(f"Game {game_id} reviewed — {len(reviews)} moves.\n")
    print(f"{'Ply':>3}  {'Move':6} {'Before':>8} {'After':>8} {'Delta':>8}  Classification")
    for r in reviews:
        before = _format_eval(r.eval_before_cp, r.eval_before_mate)
        after = _format_eval(r.eval_after_cp, r.eval_after_mate)
        delta = f"{r.eval_delta_cp / 100:+.2f}" if r.eval_delta_cp is not None else "?"
        print(f"{r.ply:>3}  {r.move_san:6} {before:>8} {after:>8} {delta:>8}  {r.classification}")

    counts: dict[str, int] = {}
    for r in reviews:
        counts[r.classification] = counts.get(r.classification, 0) + 1
    print("\nSummary: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
