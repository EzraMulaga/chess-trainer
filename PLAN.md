# Plan

Local, self-hosted chess opening trainer + game review tool. No cloud
services, no subscriptions. Backend-first: each phase is provable via CLI
before any UI exists.

Stack: SQLite (stdlib `sqlite3`), Stockfish via `python-chess`
(`chess.engine.SimpleEngine`, the modern UCI wrapper — not the deprecated
`chess.uci` module), FastAPI, static frontend (chessboard.js + chess.js +
Chart.js) served from FastAPI's static files. Lichess API integration for
real-game move-frequency stats is a possible future addition, not required
for core functionality.

Distribution: packaged as a Docker image (Stockfish baked in, no host
install needed) and published to GitHub Container Registry (GHCR) via
GitHub Actions, so it's a one-line `docker run` for anyone. This means the
repo/package goes public at that point — see Phase 7.

Commit at each phase boundary: `Phase N: <summary>`. Update
[PROGRESS.md](PROGRESS.md) alongside each commit.

## Phase 0 — Environment setup

- venv, `requirements.txt`, `.gitignore`, README skeleton.
- `scripts/verify_env.py`: confirms Python version, `python-chess` import,
  and a live Stockfish UCI round-trip (launch engine, analyse startpos,
  quit cleanly).
- Exit criteria: `python scripts/verify_env.py` passes on a fresh clone
  after `pip install -r requirements.txt` + installing the `stockfish`
  system package.

## Phase 1 — SQLite schema

Tables:
- `repertoire_positions` — FEN, side to move, source line, approved flag,
  parent position (for tree structure), SRS state fields (ease factor,
  interval, repetitions, due date) or a separate table (see below).
- `review_history` — one row per drill attempt: position FEN, timestamp,
  recalled correctly (bool), grade, resulting SRS state.
- `games` — imported PGN metadata (players, date, result, source).
- `game_moves` — per-move record for a reviewed game: ply, move SAN/UCI,
  eval before/after, eval delta, classification label.

Decision to make at this phase: whether SRS state lives directly on
`repertoire_positions` or in its own `srs_state` table keyed by FEN (cleaner
if a position can appear in multiple lines/repertoires). Lean toward a
separate table — revisit when writing the schema.

Exit criteria: schema created via a migration/init script, inspectable with
`sqlite3`, covered by a smoke test that inserts/reads one row per table.

## Phase 2 — Repertoire ingestion

- PGN import: parse a PGN into a sequence of positions, insert into
  `repertoire_positions` tagged with the source line.
- Engine-generated candidates: from a seed line, use Stockfish `multipv` to
  propose candidate continuations to a configurable depth. Needs explicit
  pruning criteria decided during this phase (e.g. eval-drop threshold
  from the best line, max branching factor per position, max depth) —
  don't leave this implicit.
- Prune/approve workflow: candidates land in a pending state; a CLI command
  approves/rejects before they become drillable.

Exit criteria: CLI can ingest a PGN and separately generate+prune an
engine-suggested line, both ending up correctly in `repertoire_positions`.

## Phase 3 — SRS drill engine

- SM-2 algorithm implementation, unit tested against known SM-2 reference
  sequences (ease factor / interval / repetition count transitions).
- CLI drill loop: pull due positions, show FEN/board, accept a move guess,
  grade recall, update SRS state, persist to `review_history`.

Exit criteria: `pytest` passes on SM-2 unit tests; a CLI session can drill
a due position end-to-end and the next-due date updates correctly.

## Phase 4 — Game review pipeline

- PGN → per-move Stockfish eval before/after each move, eval delta.
- Classification thresholds (Best / Excellent / Inaccuracy / Mistake /
  Blunder) — define concrete centipawn/eval-delta bands during this phase.
- "Brilliant" heuristic: material sacrifice + eval stays strong afterward.
  Treat as best-effort/stretch within this phase — it's inherently fuzzy
  (chess.com's own heuristic is not fully documented); don't let it block
  the rest of Phase 4 from shipping.
- CLI output first: paste/point to a PGN, get a per-move table printed to
  terminal.

Exit criteria: CLI review of a full game prints correct eval deltas and
labels for a known test game, persisted to `games`/`game_moves`.

## Phase 5 — FastAPI backend

Wrap Phases 2–4 behind HTTP endpoints (repertoire CRUD, drill session
endpoints, game review endpoint). No new business logic — this phase is
plumbing.

Exit criteria: endpoints exercised via `httpx`/`pytest` integration tests,
no manual UI needed yet.

## Phase 6 — Local web frontend

Static frontend served via FastAPI static files: chessboard.js + chess.js
for the board, Chart.js for SRS/game-review stats. Views: drill view,
repertoire browser, game review view.

Exit criteria: manually exercised in a browser against the local server —
drill a due position, browse repertoire, review a pasted game.

## Phase 7 — Dockerize + publish to GHCR

- `Dockerfile`: `python:3.12-slim` base, `apt-get install stockfish`
  (Debian ships it in `main`, no extra repo needed), install
  `requirements.txt`, copy app code, run via `uvicorn`. SQLite file lives
  under a `/data` volume mount so it persists across container recreation
  and isn't baked into the image.
- `docker-compose.yml`: single service, `./data:/data` volume, port
  `8000:8000`, `DB_PATH=/data/chess_trainer.db` env var — one-command local
  run (`docker compose up`) as an alternative to the venv workflow.
- `.github/workflows/docker-publish.yml`: on tagged release, build and push
  `ghcr.io/<owner>/chess-trainer:<tag>` + `:latest` using
  `docker/build-push-action`, authenticated with the workflow's
  `GITHUB_TOKEN` (`packages: write` permission) — no manual credentials.
- Repo/package visibility flips to **public** at this phase (required for
  others to `docker pull` from GHCR). Sanity-check before flipping: no
  secrets in history, `data/` stays gitignored so no personal SQLite/game
  data ever gets committed.
- README gets a "Run with Docker" section: `docker run` one-liner as the
  primary quickstart, venv instructions kept as the dev/contributor path.

Exit criteria: `docker compose up` runs the full app locally from a clean
clone with no host Python/Stockfish install; a tagged push produces a
pullable `ghcr.io` image; repo is public.

## Phase 8 — Polish, stats, README

Stats dashboard (retention rate, drill streaks, blunder frequency trends),
final README pass, PROGRESS.md wrap-up.

---

## Open decisions to revisit (not blocking Phase 0)

- SRS state: own table vs. columns on `repertoire_positions` (Phase 1).
- Engine-generated line pruning thresholds (Phase 2).
- Move classification centipawn bands + brilliant-move heuristic specifics
  (Phase 4).
- Docker image tagging scheme (semver tags vs. `latest`-only) and whether
  `data/` should support a bind mount default vs. named volume (Phase 7).
