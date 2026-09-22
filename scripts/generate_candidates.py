"""Phase 2: generate engine candidate continuations from a seed position.

Candidates are inserted with status 'pending' and need review via
scripts/review_candidates.py before they're drillable.

Run with:
  python scripts/generate_candidates.py <seed_fen> <repertoire_label> \
      [--stockfish PATH] [--max-ply N] [--multipv N] [--eval-drop CP] \
      [--search-depth N] [--max-candidates N] [--db PATH]
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from chess_trainer.db import DEFAULT_DB_PATH, get_connection  # noqa: E402
from chess_trainer.repertoire import CandidateConfig, generate_candidates  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("seed_fen")
    parser.add_argument("repertoire")
    parser.add_argument(
        "--stockfish",
        default=None,
        help="path to stockfish binary (default: $STOCKFISH_PATH, then PATH lookup)",
    )
    parser.add_argument("--max-ply", type=int, default=4, help="plies beyond the seed to expand")
    parser.add_argument("--multipv", type=int, default=2, help="candidate moves per position")
    parser.add_argument(
        "--eval-drop", type=int, default=50, help="max centipawn loss vs. best move to keep a candidate"
    )
    parser.add_argument("--search-depth", type=int, default=18)
    parser.add_argument("--max-candidates", type=int, default=50, help="safety cap on total nodes")
    parser.add_argument("--db", default=os.environ.get("DB_PATH", str(DEFAULT_DB_PATH)))
    args = parser.parse_args()

    engine_path = args.stockfish or os.environ.get("STOCKFISH_PATH") or shutil.which("stockfish")
    if not engine_path:
        print("Stockfish not found on PATH; pass --stockfish /path/to/stockfish")
        return 1

    config = CandidateConfig(
        max_ply=args.max_ply,
        multipv=args.multipv,
        eval_drop_cp=args.eval_drop,
        search_depth=args.search_depth,
        max_candidates=args.max_candidates,
    )

    conn = get_connection(args.db)
    ids = generate_candidates(conn, engine_path, args.seed_fen, args.repertoire, config)
    conn.close()
    print(
        f"Generated {len(ids)} positions (seed + candidates) into repertoire "
        f"'{args.repertoire}'; all but the seed are 'pending' — run "
        f"scripts/review_candidates.py to approve/reject."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
