# Chess Trainer

A local, self-hosted chess opening trainer and game-review tool. Inspired by
Chessreps and chess.com's Game Review, but fully local — no cloud services,
no subscriptions, no external API dependency for core functionality.

## Features (planned)

- **Opening repertoire trainer** — import PGN lines or generate candidate
  continuations from a seed line with Stockfish, then prune/approve which
  lines to keep.
- **Spaced repetition drilling** — SM-2 scheduling per position (by FEN),
  tracking review history and due dates.
- **Game review** — paste a full-game PGN and get per-move Stockfish
  eval/delta and a classification (Best / Excellent / Inaccuracy / Mistake /
  Blunder / Brilliant heuristic).
- Runs entirely on your machine: SQLite storage, Stockfish via
  `python-chess`, FastAPI backend, static frontend (chessboard.js + chess.js
  + Chart.js).

See [PLAN.md](PLAN.md) for the phased build order and
[PROGRESS.md](PROGRESS.md) for the current status.

## Requirements

- Python 3.10+
- [Stockfish](https://stockfishchess.org/) engine binary on `PATH` (or set
  `STOCKFISH_PATH`)
- `python3-venv` (Debian/Ubuntu: `sudo apt install python3-venv stockfish`)

## Setup

```bash
sudo apt install python3-venv stockfish   # if not already installed
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Verify your environment (Phase 0)

```bash
python scripts/verify_env.py
```

This checks your Python version, confirms `python-chess` is importable, and
launches Stockfish via UCI to run a quick analysis — confirming the full
engine pipeline works before any application code is built on top of it.

## Status

Phase 0: environment setup. See [PROGRESS.md](PROGRESS.md).
