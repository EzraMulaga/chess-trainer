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

## Run with Docker

No Python or Stockfish install needed — both are baked into the image.

```bash
docker run -d -p 8000:8000 -v "$(pwd)/data:/data" ghcr.io/ezramulaga/chess-trainer:latest
```

Or with the repo checked out:

```bash
docker compose up
```

Either way, open `http://127.0.0.1:8000/`. `./data` on the host holds the
SQLite file, so it survives container restarts/recreation. Set `DB_PATH`
to change where the db file lives inside the container.

Images are published to GHCR on tagged releases
(`.github/workflows/docker-publish.yml`) — `:latest` plus a `:vX.Y.Z` tag
per release.

## Development setup (without Docker)

- Python 3.10+
- [Stockfish](https://stockfishchess.org/) engine binary on `PATH` (or set
  `STOCKFISH_PATH`)
- `python3-venv` (Debian/Ubuntu: `sudo apt install python3-venv stockfish`)

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

## Running the API server

```bash
python scripts/init_db.py          # first time only, creates data/chess_trainer.db
uvicorn chess_trainer.api:app --reload
```

Open `http://127.0.0.1:8000/` for the web UI (Drill / Repertoire / Game
Review tabs), or `http://127.0.0.1:8000/docs` for interactive API docs.
`DB_PATH` and `STOCKFISH_PATH` env vars override the defaults (gitignored
`data/` directory, `stockfish` on `PATH`).

The frontend (`static/`) is plain HTML/CSS/vanilla JS — no build step.
chessboard.js, chess.js, jQuery (chessboard.js's peer dependency), and
Chart.js are vendored under `static/vendor/` so nothing loads from a CDN
at runtime.

## CLI tools

- `scripts/import_pgn.py <pgn_file> <repertoire_label>`
- `scripts/generate_candidates.py <seed_fen> <repertoire_label>`
- `scripts/review_candidates.py [repertoire_label]` — approve/reject prompt
- `scripts/drill.py [repertoire_label]` — SRS drill loop
- `scripts/review_game.py <pgn_file>` — per-move game review table

## Status

Phase 7: Dockerize + publish to GHCR. See [PROGRESS.md](PROGRESS.md).
