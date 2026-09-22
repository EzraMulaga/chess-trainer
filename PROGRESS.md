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
