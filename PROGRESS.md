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

## Phase 5 — FastAPI backend (complete)

- `chess_trainer/api.py`: thin HTTP wrapper over Phases 2-4, no new
  business logic. Endpoints: `/health`, `/repertoire/import-pgn`,
  `/repertoire/generate-candidates`, `/repertoire/pending`,
  `/repertoire/positions/{id}/status`, `/repertoire/positions/{id}/line`,
  `/drill/due`, `/drill/positions/{id}/answer`, `/games/review`,
  `/games/{id}`. `DB_PATH` / `STOCKFISH_PATH` env vars override the
  CLI-script defaults.
- Found and fixed a real bug while wiring this up (not just a test
  artifact): FastAPI dispatches sync dependencies and sync endpoints via a
  thread pool, so the OS thread that opens a DB connection in `get_db()`
  isn't guaranteed to be the same thread the endpoint runs on — sqlite3
  rejects that by default. Fixed in `chess_trainer/db.py` by passing
  `check_same_thread=False` to `sqlite3.connect()`; safe here because
  usage within one request stays sequential, never concurrent.
- `tests/test_api.py`: 9 tests via `fastapi.testclient.TestClient`, with
  `get_db` overridden to share one in-memory connection across a test's
  requests (a fresh `:memory:` connection per request would each be a
  separate empty database). Covers the full import → drill → answer
  flow, status transitions + 400/404s, a 503 when Stockfish is
  unavailable (dependency override), and live-Stockfish tests for
  candidate generation and game review (skipped without a stockfish
  binary on PATH).
- Verified beyond the test client: ran `uvicorn chess_trainer.api:app`
  for real and hit `/health`, `/repertoire/import-pgn`, `/drill/due`,
  `/drill/positions/{id}/answer`, and `/games/review` with `curl` against
  a live server — all matched the CLI/test behavior.

## Phase 6 — Local web frontend (complete)

- `static/`: plain HTML/CSS/vanilla-JS app, no build step. Three tabs —
  Drill, Repertoire, Game Review — served via FastAPI's `StaticFiles`
  mount at `/static`, with `/` redirecting to `/static/index.html`
  (`chess_trainer/api.py`).
- Vendored locally under `static/vendor/` (fetched at build time, loaded
  from disk at runtime, no CDN dependency): chessboard.js 1.0.0 + its 12
  wikipedia-set piece sprites, chess.js 0.10.3 (the version chessboard.js's
  official examples pair with), jQuery 3.7.1, Chart.js 4.5.1.
- Drill view: chessboard.js drag-and-drop, chess.js validates legality
  client-side (snaps back illegal drops), a legal drop submits straight to
  `/drill/positions/{id}/answer` — no separate submit button. Board
  orientation is derived from the FEN's side-to-move field.
- Repertoire view: PGN import form, candidate-generation form (all
  `CandidateConfig` knobs exposed), pending-candidates list with
  approve/reject buttons — a browser port of `scripts/review_candidates.py`.
- Game review view: results table color-coded by classification, a
  Chart.js eval-over-time line chart, and a small board that updates on
  row click. The review API only returns evals/classifications (no FEN
  per move), so the board is reconstructed client-side by replaying the
  returned `move_uci` sequence through chess.js — no backend change
  needed for this.
- **Real bug found and fixed via browser testing, not caught by curl or
  the Python test suite**: chessboard.js 1.0.0 requires jQuery as an
  undocumented-in-my-notes peer dependency (`$.fn` extension pattern
  internally). Without it, `Chessboard(...)` throws
  `Cannot read properties of undefined (reading 'fn')` and the whole page
  breaks on load. Static-asset curl checks and the FastAPI test suite
  both stayed green through this — only driving a real browser surfaced
  it. Fixed by vendoring jQuery and loading it before chessboard.js.
- `tests/test_api.py` gained `test_root_redirects_to_static_index` and
  `test_static_frontend_assets_are_served` (checks all vendored files +
  app JS/CSS resolve to 200) as a permanent regression check for the
  static-serving wiring.
- Verified with a headless-Chromium Playwright driver (no project `run`
  skill existed yet, so used the generic browser-driven pattern; Chromium
  had to be downloaded — no system browser was preinstalled): loaded the
  page (zero console errors after the jQuery fix), imported a PGN,
  dragged a piece on the drill board end-to-end to a "Correct! Next
  review in 1 day(s)" result, generated + approved engine candidates
  through the UI, and ran a full game review confirming the blunder
  classification, eval chart, and click-to-see-board all rendered
  correctly. Screenshots inspected directly, not just asserted on.

## Phase 7 — Dockerize + publish to GHCR (complete)

- `Dockerfile`: `python:3.12-slim` + `apt-get install stockfish`, installs
  `requirements.txt`, copies `chess_trainer/`/`static/`/`scripts/`, bakes
  in `DB_PATH=/data/chess_trainer.db` and `STOCKFISH_PATH=/usr/games/stockfish`
  as defaults, `/data` declared as a volume, healthcheck against
  `/health`. `CMD` runs `scripts/init_db.py` (idempotent —
  `CREATE TABLE IF NOT EXISTS` throughout) before `uvicorn`, so the schema
  is always present on boot without a separate manual step.
- `docker-compose.yml`: single service, `./data:/data` bind mount, port
  `8000:8000`. `.dockerignore` keeps `venv/`, `.git/`, `tests/`, etc. out
  of the build context.
- **Two real bugs found by actually building and running the container**,
  not caught by the existing test suite (which never runs against a
  container):
  1. `scripts/init_db.py` ignored the `DB_PATH` env var entirely, only
     checking `sys.argv`. Inside the container this meant the schema got
     created at `/app/data/chess_trainer.db` (the package-relative
     default) while `chess_trainer/api.py` correctly read `/data/...` from
     `DB_PATH` — two different files, neither matching what the other
     expected, and the one actually mounted as a volume (`/data`) stayed
     empty. Confirmed via `docker exec` inspection before fixing.
  2. `scripts/generate_candidates.py` and `scripts/review_game.py` looked
     up Stockfish via `shutil.which("stockfish")` only, never checking
     `STOCKFISH_PATH`. Debian installs Stockfish to `/usr/games/stockfish`,
     and `/usr/games` isn't on `PATH` in a minimal non-login container
     shell — confirmed via `docker exec sh -c 'echo $PATH'`. Anyone
     `docker exec`-ing in to use these CLI tools directly would have hit
     "Stockfish not found" despite `STOCKFISH_PATH` being set correctly.
  Fixed all five CLI scripts (`init_db.py`, `import_pgn.py`, `drill.py`,
  `review_candidates.py`, `generate_candidates.py`, `review_game.py`) to
  check the env var first, consistent with the pattern `api.py` already
  used. Re-verified: rebuilt, confirmed the db now lands in the mounted
  `/data` volume, and confirmed data survives a full `docker compose down`
  + `up` (container recreation) — a game reviewed before the restart was
  still readable after.
- `.github/workflows/docker-publish.yml`: on a `v*.*.*` tag push, builds
  and pushes `ghcr.io/<owner>/chess-trainer:latest` +
  `:<version>` via `docker/build-push-action`, authenticated with the
  workflow's own `GITHUB_TOKEN` (no manual secrets).
- README restructured: "Run with Docker" is now the primary quickstart
  (`docker run` one-liner, or `docker compose up`), venv instructions
  moved to a "Development setup (without Docker)" section.
- Verified end-to-end against the built image (not just `docker build`
  succeeding): imported a PGN via the API, ran a live-Stockfish game
  review through the container and got the correct blunder classification
  back, confirmed the frontend is served, and confirmed persistence across
  a restart — all through the actual running container, same as the
  "docker compose up runs the full app locally... a tagged push produces
  a pullable ghcr.io image" exit criteria.
- Confirmed with the user before the consequential step: repo was already
  public (unexpected given earlier context saying private — user confirmed
  that was intentional on their end). Pushed 6 local commits to
  `origin/main`, tagged `v0.1.0`, pushed the tag. The workflow ran and
  succeeded in ~1 minute. Verified the published image for real, not just
  the workflow's green checkmark: pulled `ghcr.io/ezramulaga/chess-trainer:latest`
  fresh (after removing all local images), ran it standalone, and hit
  `/health` and `/` successfully — proving it's genuinely public and
  pullable, matching the "a tagged push produces a pullable ghcr.io image"
  exit criteria exactly.
