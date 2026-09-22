"""Phase 4: game review — per-move Stockfish eval and move classification."""
from __future__ import annotations

import io
import sqlite3
from dataclasses import dataclass
from typing import Optional

import chess
import chess.engine
import chess.pgn

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
}


@dataclass
class ReviewConfig:
    search_depth: int = 16
    # Centipawn-loss bands (from the mover's own perspective), each upper-inclusive.
    best_cp: int = 20
    excellent_cp: int = 50
    inaccuracy_cp: int = 100
    mistake_cp: int = 200
    # above mistake_cp => blunder
    # "Brilliant" heuristic — best-effort, see PLAN.md Phase 4 notes.
    brilliant_max_loss_cp: int = 25
    brilliant_min_sacrifice_cp: int = 300


@dataclass
class MoveReview:
    ply: int
    move_san: str
    move_uci: str
    eval_before_cp: Optional[int]
    eval_before_mate: Optional[int]
    eval_after_cp: Optional[int]
    eval_after_mate: Optional[int]
    eval_delta_cp: Optional[int]
    classification: str


def _score_parts(score: chess.engine.PovScore) -> tuple[Optional[int], Optional[int]]:
    white_score = score.white()
    if white_score.is_mate():
        return None, white_score.mate()
    return white_score.score(), None


def _white_cp_equiv(score: chess.engine.PovScore) -> int:
    """White's-perspective centipawn value, with mate scores folded onto the
    same scale via a large sentinel so classification math stays uniform."""
    return score.white().score(mate_score=100_000)


def _material_for(board: chess.Board, color: chess.Color) -> int:
    return sum(
        len(board.pieces(piece_type, color)) * value for piece_type, value in PIECE_VALUES.items()
    )


def classify(loss_cp: int, config: ReviewConfig) -> str:
    if loss_cp <= config.best_cp:
        return "best"
    if loss_cp <= config.excellent_cp:
        return "excellent"
    if loss_cp <= config.inaccuracy_cp:
        return "inaccuracy"
    if loss_cp <= config.mistake_cp:
        return "mistake"
    return "blunder"


def _maybe_upgrade_to_brilliant(
    board_before: chess.Board,
    move: chess.Move,
    board_after: chess.Board,
    classification: str,
    loss_cp: int,
    info_after: dict,
    config: ReviewConfig,
) -> str:
    """A sound (best/excellent) move that knowingly sacrifices material and
    still holds a strong evaluation. Inherently fuzzy — see PLAN.md."""
    if classification not in ("best", "excellent"):
        return classification
    if loss_cp > config.brilliant_max_loss_cp:
        return classification
    if board_before.legal_moves.count() <= 1:
        return classification  # forced move, not a real choice

    mover = board_before.turn
    material_before = _material_for(board_before, mover)

    board_two_ply = board_after.copy()
    pv = info_after.get("pv")
    if pv:
        reply = pv[0]
        if board_two_ply.is_legal(reply):
            board_two_ply.push(reply)

    material_after = _material_for(board_two_ply, mover)
    if material_before - material_after >= config.brilliant_min_sacrifice_cp:
        return "brilliant"
    return classification


def _insert_game(conn: sqlite3.Connection, pgn_text: str, headers) -> int:
    cur = conn.execute(
        "INSERT INTO games (pgn, white, black, result, played_at, source) VALUES (?, ?, ?, ?, ?, ?)",
        (pgn_text, headers.get("White"), headers.get("Black"), headers.get("Result"), headers.get("Date"), "manual_paste"),
    )
    return cur.lastrowid


def _insert_game_move(conn: sqlite3.Connection, game_id: int, review: MoveReview) -> None:
    conn.execute(
        """
        INSERT INTO game_moves
            (game_id, ply, move_san, move_uci, eval_before_cp, eval_before_mate,
             eval_after_cp, eval_after_mate, eval_delta_cp, classification)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            game_id, review.ply, review.move_san, review.move_uci,
            review.eval_before_cp, review.eval_before_mate,
            review.eval_after_cp, review.eval_after_mate,
            review.eval_delta_cp, review.classification,
        ),
    )


def review_game(
    conn: sqlite3.Connection,
    engine_path: str,
    pgn_text: str,
    config: ReviewConfig = ReviewConfig(),
) -> tuple[int, list[MoveReview]]:
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("could not parse PGN")

    game_id = _insert_game(conn, pgn_text, game.headers)

    board = game.board()
    reviews: list[MoveReview] = []

    with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
        limit = chess.engine.Limit(depth=config.search_depth)
        info_before = engine.analyse(board, limit)

        for ply, move in enumerate(game.mainline_moves(), start=1):
            board_before = board.copy()
            move_san = board_before.san(move)
            mover = board_before.turn

            eval_before_cp, eval_before_mate = _score_parts(info_before["score"])
            white_before = _white_cp_equiv(info_before["score"])

            board.push(move)
            info_after = engine.analyse(board, limit)
            eval_after_cp, eval_after_mate = _score_parts(info_after["score"])
            white_after = _white_cp_equiv(info_after["score"])

            loss_cp = max(0, (white_before - white_after) if mover else (white_after - white_before))
            classification = classify(loss_cp, config)
            classification = _maybe_upgrade_to_brilliant(
                board_before, move, board, classification, loss_cp, info_after, config
            )

            review = MoveReview(
                ply=ply,
                move_san=move_san,
                move_uci=move.uci(),
                eval_before_cp=eval_before_cp,
                eval_before_mate=eval_before_mate,
                eval_after_cp=eval_after_cp,
                eval_after_mate=eval_after_mate,
                eval_delta_cp=white_after - white_before,
                classification=classification,
            )
            reviews.append(review)
            _insert_game_move(conn, game_id, review)

            info_before = info_after

    conn.commit()
    return game_id, reviews
