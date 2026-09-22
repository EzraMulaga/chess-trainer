# Progress Log

## Phase 0 — Environment setup (complete)

- 2026-09-22: Project structure created (`chess_trainer/`, `tests/`,
  `scripts/`), `requirements.txt`, `.gitignore`, `README.md`, `PLAN.md`.
- `scripts/verify_env.py` written and confirmed to fail gracefully with
  actionable messages when `python-chess`/Stockfish are missing.
- `python3-venv`/`stockfish` install hit a stale apt index (404 on
  `python3.14-venv`); fixed with `sudo apt update` then reinstall.
- `venv/` had to be recreated once — the first `python3 -m venv venv` ran
  before `python3-venv` actually landed, leaving a venv with no `pip`.
- `scripts/verify_env.py` passes cleanly: Python 3.14.4, python-chess
  1.11.2, Stockfish at `/usr/games/stockfish`, live UCI analysis on the
  startpos (depth 15, score +39, bestmove e2e4).

## Plan update — 2026-09-22

- Added Phase 7 (Dockerize + publish to GHCR via GitHub Actions), pushing
  the former Phase 7 (Polish/stats/README) to Phase 8. Repo/package will
  go public at Phase 7. No code changes yet — this phase is future work,
  still on Phase 1 next.

## Phase 1 — SQLite schema (complete)

- `chess_trainer/schema.sql`: `repertoire_positions`, `srs_state`,
  `review_history`, `games`, `game_moves`. Resolved the open decision from
  PLAN.md: `srs_state` is its own table keyed by `position_id` (FK to
  `repertoire_positions`, cascading delete), not columns bolted onto the
  position row.
- Position identity uses EPD (FEN without halfmove/fullmove counters), so
  the same opening position reached at different points in time still
  compares equal.
- `chess_trainer/db.py`: `get_connection()` / `init_db()`.
  `scripts/init_db.py`: CLI entry point, defaults to
  `data/chess_trainer.db` (gitignored).
- `tests/test_db.py`: 4 tests (table creation, one-row-per-table
  insert/read, cascade delete, CHECK constraint rejection) — all passing.
  Verified `scripts/init_db.py` end-to-end against a real file, inspected
  with `sqlite3 .tables` / `.schema`.

## Phase 2 — Repertoire ingestion (complete)

- `chess_trainer/repertoire.py`: `import_pgn()` (PGN mainline → chained
  `repertoire_positions` rows, defaults to `status='approved'` since these
  are lines the user already chose), `generate_candidates()` (Stockfish
  `multipv` breadth-first expansion from a seed FEN, status `'pending'`),
  `list_pending()` / `set_status()` / `line_to_root()` for the
  approve/reject workflow.
- Pruning defaults settled without further input (flagged as tunable, not
  asked again): `max_ply=4`, `multipv=2`, `eval_drop_cp=50`,
  `search_depth=18`, `max_candidates=50` safety cap. All overridable via
  CLI flags on `scripts/generate_candidates.py`.
- Eval-drop comparison uses each node's `score.relative` (mover's point of
  view, matches multipv's best-first ordering); stored `eval_cp`/`eval_mate`
  stay in White's-perspective convention per the schema comment.
- CLI: `scripts/import_pgn.py`, `scripts/generate_candidates.py`,
  `scripts/review_candidates.py` (interactive a/r/s prompt per pending
  candidate, shows the SAN line leading to it).
- `tests/test_repertoire.py`: 5 tests, including a live-Stockfish
  `generate_candidates` test (skipped if `stockfish` isn't on PATH). Also
  ran the full pipeline by hand against a real db file: imported a 5-move
  London PGN (10 rows, all approved), generated 6 candidates from a
  mid-line seed (multipv=2, depth=2, capped at 8), approved/rejected via
  the CLI prompt — final table state inspected with `sqlite3` and matched
  expectations exactly.
