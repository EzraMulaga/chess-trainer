"""Phase 2: repertoire ingestion — PGN import and engine-generated candidates."""
from __future__ import annotations

import io
import sqlite3
from dataclasses import dataclass
from typing import Optional

import chess
import chess.engine
import chess.pgn


def _epd(board: chess.Board) -> str:
    return board.epd()


def _insert_position(
    conn: sqlite3.Connection,
    epd: str,
    parent_id: Optional[int],
    move_san: Optional[str],
    move_uci: Optional[str],
    ply: int,
    repertoire: str,
    source: str,
    status: str,
    eval_cp: Optional[int] = None,
    eval_mate: Optional[int] = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO repertoire_positions
            (epd, parent_id, move_san, move_uci, ply, repertoire, source, status, eval_cp, eval_mate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (epd, parent_id, move_san, move_uci, ply, repertoire, source, status, eval_cp, eval_mate),
    )
    return cur.lastrowid


def import_pgn(
    conn: sqlite3.Connection, pgn_text: str, repertoire: str, status: str = "approved"
) -> list[int]:
    """Parse a PGN's mainline and insert each position, chained by parent_id.

    PGN import is treated as lines the user has already chosen, so it
    defaults to 'approved' rather than going through the prune workflow.
    Returns the inserted position ids, root to leaf.
    """
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("could not parse PGN")

    board = game.board()
    root_id = _insert_position(
        conn, _epd(board), None, None, None, 0, repertoire, "pgn_import", status
    )
    inserted_ids = [root_id]
    parent_id = root_id

    for ply, move in enumerate(game.mainline_moves(), start=1):
        move_san = board.san(move)
        board.push(move)
        position_id = _insert_position(
            conn, _epd(board), parent_id, move_san, move.uci(), ply, repertoire, "pgn_import", status
        )
        inserted_ids.append(position_id)
        parent_id = position_id

    conn.commit()
    return inserted_ids


@dataclass
class CandidateConfig:
    max_ply: int = 4
    """Plies beyond the seed position to expand."""
    multipv: int = 2
    """Candidate moves considered per position (breadth cap)."""
    eval_drop_cp: int = 50
    """Max centipawn loss vs. the best move at a node to keep a candidate."""
    search_depth: int = 18
    """Stockfish search depth per position."""
    max_candidates: int = 50
    """Safety cap on total positions inserted (seed included)."""


def generate_candidates(
    conn: sqlite3.Connection,
    engine_path: str,
    seed_fen: str,
    repertoire: str,
    config: CandidateConfig = CandidateConfig(),
) -> list[int]:
    """Expand candidate continuations from a seed position via Stockfish multipv.

    Inserts the seed position itself (status 'approved' — it's assumed to
    already be part of the repertoire) plus generated descendants (status
    'pending'), pruned to moves within `eval_drop_cp` of the best move at
    each node, breadth capped by `multipv`, depth capped by `max_ply`, and
    total nodes capped by `max_candidates`. Expansion is breadth-first.

    Returns the inserted position ids (seed included).
    """
    board = chess.Board(seed_fen)
    seed_id = _insert_position(
        conn, _epd(board), None, None, None, 0, repertoire, "engine_generated", "approved"
    )
    inserted_ids = [seed_id]

    with chess.engine.SimpleEngine.popen_uci(engine_path) as engine:
        frontier = [(board, seed_id, 0)]
        while frontier and len(inserted_ids) < config.max_candidates:
            parent_board, parent_id, ply = frontier.pop(0)
            if ply >= config.max_ply or parent_board.is_game_over():
                continue

            legal_count = parent_board.legal_moves.count()
            multipv = min(config.multipv, legal_count)
            limit = chess.engine.Limit(depth=config.search_depth)
            infos = engine.analyse(parent_board, limit, multipv=multipv)
            if isinstance(infos, dict):
                infos = [infos]

            best_relative_cp = infos[0]["score"].relative.score(mate_score=100_000)

            for entry in infos:
                if len(inserted_ids) >= config.max_candidates:
                    break
                relative_cp = entry["score"].relative.score(mate_score=100_000)
                if best_relative_cp - relative_cp > config.eval_drop_cp:
                    continue

                move = entry["pv"][0]
                child_board = parent_board.copy()
                move_san = child_board.san(move)
                child_board.push(move)

                white_score = entry["score"].white()
                eval_cp = None if white_score.is_mate() else white_score.score()
                eval_mate = white_score.mate() if white_score.is_mate() else None

                child_id = _insert_position(
                    conn,
                    _epd(child_board),
                    parent_id,
                    move_san,
                    move.uci(),
                    ply + 1,
                    repertoire,
                    "engine_generated",
                    "pending",
                    eval_cp,
                    eval_mate,
                )
                inserted_ids.append(child_id)
                frontier.append((child_board, child_id, ply + 1))

    conn.commit()
    return inserted_ids


def list_pending(conn: sqlite3.Connection, repertoire: Optional[str] = None) -> list[sqlite3.Row]:
    query = "SELECT * FROM repertoire_positions WHERE status = 'pending'"
    params: list[str] = []
    if repertoire:
        query += " AND repertoire = ?"
        params.append(repertoire)
    query += " ORDER BY ply, id"
    return conn.execute(query, params).fetchall()


def set_status(conn: sqlite3.Connection, position_id: int, status: str) -> None:
    if status not in ("pending", "approved", "rejected"):
        raise ValueError(f"invalid status: {status}")
    conn.execute("UPDATE repertoire_positions SET status = ? WHERE id = ?", (status, position_id))
    conn.commit()


def line_to_root(conn: sqlite3.Connection, position_id: int) -> list[sqlite3.Row]:
    """Return the chain of positions from the repertoire root to position_id, inclusive."""
    chain = []
    row = conn.execute("SELECT * FROM repertoire_positions WHERE id = ?", (position_id,)).fetchone()
    while row is not None:
        chain.append(row)
        if row["parent_id"] is None:
            break
        row = conn.execute(
            "SELECT * FROM repertoire_positions WHERE id = ?", (row["parent_id"],)
        ).fetchone()
    chain.reverse()
    return chain
