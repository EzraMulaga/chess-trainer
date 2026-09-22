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

## Phase 3 — SRS drill engine (complete)

- `chess_trainer/srs.py`: `sm2()` (pure SM-2 function, quality 0-5, ease
  floored at 1.3), `sync_srs_state()` (creates `srs_state` rows for
  newly-approved, non-root positions — called automatically at the start
  of a drill session rather than needing a manual step), `get_due_positions()`,
  `board_before_move()` (reconstructs the pre-move board from the parent's
  stored EPD), `check_answer()` (accepts SAN or UCI), `grade_review()`
  (updates `srs_state` + logs `review_history`).
  Timestamps standardized on SQLite's `CURRENT_TIMESTAMP` string format
  (space-separated, no timezone) throughout, to avoid a format mismatch
  between DB-defaulted and Python-computed `due_at` values that would have
  broken due-date ordering.
- `scripts/drill.py`: CLI loop — shows the board, takes a move guess,
  correct answers prompt for an SM-2 quality (3-5, default 4), incorrect
  answers auto-grade 0 (no point asking a human to rate a wrong answer's
  difficulty).
- `tests/test_srs.py`: 13 tests. SM-2 verified against hand-computed
  reference sequences (successful-review chain 2.5→2.6→2.7→2.8, EF-neutral
  quality-4 grade, EF floor at 1.3, failing-grade reset, out-of-range
  quality rejection), plus DB-level tests for sync/due-query/grading.
  Also ran `scripts/drill.py` by hand against a real db (3 correct + 1
  incorrect answer) and confirmed `srs_state`/`review_history` matched the
  SM-2 math exactly via `sqlite3`.

## Phase 4 — Game review pipeline (complete)

- `chess_trainer/review.py`: `review_game()` walks a PGN's mainline,
  analysing each position with Stockfish once (reuses the "after" analysis
  of move N as the "before" analysis of move N+1, halving engine calls).
  `classify()` uses fixed centipawn-loss bands, measured from the mover's
  own perspective so White/Black are handled identically: best ≤20cp,
  excellent ≤50cp, inaccuracy ≤100cp, mistake ≤200cp, blunder beyond that.
  Mate scores are folded onto the same integer scale via a 100,000cp
  sentinel rather than special-cased, keeping the classification math
  uniform. All thresholds live in `ReviewConfig`, picked as reasonable
  defaults per PLAN.md rather than settled with further back-and-forth —
  tunable later if they feel off in practice.
- "Brilliant" heuristic (`_maybe_upgrade_to_brilliant`, best-effort per
  PLAN.md): only applies to already-sound (best/excellent) moves that
  aren't forced (>1 legal move available), and requires a genuine net
  material sacrifice (≥300cp) still standing after the opponent's engine-
  suggested best reply two plies out.
- `scripts/review_game.py`: CLI — prints a per-move eval/delta/
  classification table plus a summary count, persists to `games` +
  `game_moves`.
- `tests/test_review.py`: 6 tests — classification band edges, three
  brilliant-heuristic branches (genuine sacrifice / no sacrifice / forced
  move) using hand-built positions and fabricated engine replies (no
  engine needed for these), plus a live-Stockfish end-to-end test using a
  scripted queen blunder (2...Qh5 3.Qxe5?? Nxe5) that must classify as
  'blunder'. Verified `scripts/review_game.py` by hand against the same
  game — the CLI table and persisted `game_moves` rows both matched.
