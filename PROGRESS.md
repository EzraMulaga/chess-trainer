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
