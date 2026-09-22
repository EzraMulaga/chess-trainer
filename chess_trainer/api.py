"""Phase 5: FastAPI backend — wraps Phases 2-4 behind HTTP endpoints.

No new business logic lives here; every handler delegates to
chess_trainer.repertoire / .srs / .review.
"""
import os
import shutil
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from chess_trainer.db import DEFAULT_DB_PATH, get_connection
from chess_trainer.repertoire import CandidateConfig, generate_candidates, import_pgn, line_to_root, list_pending, set_status
from chess_trainer.review import MoveReview, ReviewConfig, review_game
from chess_trainer.srs import board_before_move, check_answer, get_due_positions, grade_review, sync_srs_state

DB_PATH = os.environ.get("DB_PATH", str(DEFAULT_DB_PATH))
STOCKFISH_PATH = os.environ.get("STOCKFISH_PATH") or shutil.which("stockfish")
STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI(title="Chess Trainer API")

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/static/index.html")


def get_db():
    conn = get_connection(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def require_engine_path() -> str:
    if not STOCKFISH_PATH:
        raise HTTPException(status_code=503, detail="Stockfish not available on the server")
    return STOCKFISH_PATH


@app.get("/health")
def health():
    return {"status": "ok"}


# --- repertoire ingestion / prune workflow --------------------------------


class ImportPgnRequest(BaseModel):
    pgn: str
    repertoire: str


class ImportPgnResponse(BaseModel):
    position_ids: list[int]


class GenerateCandidatesRequest(BaseModel):
    seed_fen: str
    repertoire: str
    max_ply: int = 4
    multipv: int = 2
    eval_drop_cp: int = 50
    search_depth: int = 18
    max_candidates: int = 50


class GenerateCandidatesResponse(BaseModel):
    position_ids: list[int]


class PositionOut(BaseModel):
    id: int
    epd: str
    parent_id: Optional[int]
    move_san: Optional[str]
    move_uci: Optional[str]
    ply: int
    repertoire: str
    source: str
    status: str
    eval_cp: Optional[int]
    eval_mate: Optional[int]


class StatusUpdateRequest(BaseModel):
    status: str


@app.post("/repertoire/import-pgn", response_model=ImportPgnResponse)
def api_import_pgn(req: ImportPgnRequest, conn: sqlite3.Connection = Depends(get_db)):
    try:
        ids = import_pgn(conn, req.pgn, req.repertoire)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ImportPgnResponse(position_ids=ids)


@app.post("/repertoire/generate-candidates", response_model=GenerateCandidatesResponse)
def api_generate_candidates(
    req: GenerateCandidatesRequest,
    conn: sqlite3.Connection = Depends(get_db),
    engine_path: str = Depends(require_engine_path),
):
    config = CandidateConfig(
        max_ply=req.max_ply,
        multipv=req.multipv,
        eval_drop_cp=req.eval_drop_cp,
        search_depth=req.search_depth,
        max_candidates=req.max_candidates,
    )
    try:
        ids = generate_candidates(conn, engine_path, req.seed_fen, req.repertoire, config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return GenerateCandidatesResponse(position_ids=ids)


@app.get("/repertoire/pending", response_model=list[PositionOut])
def api_list_pending(repertoire: Optional[str] = None, conn: sqlite3.Connection = Depends(get_db)):
    return [PositionOut(**dict(row)) for row in list_pending(conn, repertoire)]


@app.post("/repertoire/positions/{position_id}/status", response_model=PositionOut)
def api_set_status(position_id: int, req: StatusUpdateRequest, conn: sqlite3.Connection = Depends(get_db)):
    try:
        set_status(conn, position_id, req.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    row = conn.execute("SELECT * FROM repertoire_positions WHERE id = ?", (position_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="position not found")
    return PositionOut(**dict(row))


@app.get("/repertoire/positions/{position_id}/line", response_model=list[PositionOut])
def api_line_to_root(position_id: int, conn: sqlite3.Connection = Depends(get_db)):
    chain = line_to_root(conn, position_id)
    if not chain:
        raise HTTPException(status_code=404, detail="position not found")
    return [PositionOut(**dict(row)) for row in chain]


# --- SRS drilling ----------------------------------------------------------


class DuePositionOut(BaseModel):
    id: int
    fen: str
    move_san: str
    move_uci: str
    repertoire: str
    ease_factor: float
    interval_days: int
    repetitions: int
    due_at: str


class AnswerRequest(BaseModel):
    move: str
    quality: Optional[int] = None  # only used when correct; defaults to 4


class AnswerResponse(BaseModel):
    correct: bool
    correct_move_san: str
    ease_factor: float
    interval_days: int
    repetitions: int


@app.get("/drill/due", response_model=list[DuePositionOut])
def api_get_due(repertoire: Optional[str] = None, conn: sqlite3.Connection = Depends(get_db)):
    sync_srs_state(conn, repertoire)
    due = []
    for row in get_due_positions(conn, repertoire):
        board = board_before_move(conn, row)
        due.append(
            DuePositionOut(
                id=row["id"],
                fen=board.fen(),
                move_san=row["move_san"],
                move_uci=row["move_uci"],
                repertoire=row["repertoire"],
                ease_factor=row["ease_factor"],
                interval_days=row["interval_days"],
                repetitions=row["repetitions"],
                due_at=row["due_at"],
            )
        )
    return due


@app.post("/drill/positions/{position_id}/answer", response_model=AnswerResponse)
def api_answer(position_id: int, req: AnswerRequest, conn: sqlite3.Connection = Depends(get_db)):
    row = conn.execute("SELECT * FROM repertoire_positions WHERE id = ?", (position_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="position not found")

    board = board_before_move(conn, row)
    correct = check_answer(board, row["move_uci"], req.move)
    if correct:
        quality = max(3, min(5, req.quality if req.quality is not None else 4))
    else:
        quality = 0

    try:
        result = grade_review(conn, position_id, quality, correct)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return AnswerResponse(
        correct=correct,
        correct_move_san=row["move_san"],
        ease_factor=result.ease_factor,
        interval_days=result.interval_days,
        repetitions=result.repetitions,
    )


# --- game review -------------------------------------------------------------


class ReviewGameRequest(BaseModel):
    pgn: str
    search_depth: int = 16


class MoveReviewOut(BaseModel):
    ply: int
    move_san: str
    move_uci: str
    eval_before_cp: Optional[int]
    eval_before_mate: Optional[int]
    eval_after_cp: Optional[int]
    eval_after_mate: Optional[int]
    eval_delta_cp: Optional[int]
    classification: str


class ReviewGameResponse(BaseModel):
    game_id: int
    moves: list[MoveReviewOut]


class GameOut(BaseModel):
    id: int
    pgn: str
    white: Optional[str]
    black: Optional[str]
    result: Optional[str]
    played_at: Optional[str]
    moves: list[MoveReviewOut]


def _move_review_out(review: MoveReview) -> MoveReviewOut:
    return MoveReviewOut(
        ply=review.ply,
        move_san=review.move_san,
        move_uci=review.move_uci,
        eval_before_cp=review.eval_before_cp,
        eval_before_mate=review.eval_before_mate,
        eval_after_cp=review.eval_after_cp,
        eval_after_mate=review.eval_after_mate,
        eval_delta_cp=review.eval_delta_cp,
        classification=review.classification,
    )


@app.post("/games/review", response_model=ReviewGameResponse)
def api_review_game(
    req: ReviewGameRequest,
    conn: sqlite3.Connection = Depends(get_db),
    engine_path: str = Depends(require_engine_path),
):
    config = ReviewConfig(search_depth=req.search_depth)
    try:
        game_id, reviews = review_game(conn, engine_path, req.pgn, config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ReviewGameResponse(game_id=game_id, moves=[_move_review_out(r) for r in reviews])


@app.get("/games/{game_id}", response_model=GameOut)
def api_get_game(game_id: int, conn: sqlite3.Connection = Depends(get_db)):
    game_row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    if game_row is None:
        raise HTTPException(status_code=404, detail="game not found")
    move_rows = conn.execute(
        "SELECT * FROM game_moves WHERE game_id = ? ORDER BY ply", (game_id,)
    ).fetchall()
    return GameOut(
        id=game_row["id"],
        pgn=game_row["pgn"],
        white=game_row["white"],
        black=game_row["black"],
        result=game_row["result"],
        played_at=game_row["played_at"],
        moves=[MoveReviewOut(**dict(row)) for row in move_rows],
    )
