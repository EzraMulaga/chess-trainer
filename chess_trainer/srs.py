"""Phase 3: SM-2 spaced repetition and the drill-session data access it needs."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import chess

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"  # matches SQLite's CURRENT_TIMESTAMP output


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)


@dataclass
class SM2Result:
    ease_factor: float
    interval_days: int
    repetitions: int


def sm2(quality: int, ease_factor: float, interval_days: int, repetitions: int) -> SM2Result:
    """Classic SM-2: quality 0-5 (>=3 counts as recalled), returns the updated state.

    A failing grade (quality < 3) resets repetitions and interval to
    restart learning, but still adjusts ease_factor via the same formula
    the original SuperMemo-2 algorithm uses — it isn't skipped on failure.
    ease_factor is floored at 1.3 regardless of grade.
    """
    if not 0 <= quality <= 5:
        raise ValueError("quality must be between 0 and 5")

    if quality >= 3:
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = round(interval_days * ease_factor)
        new_repetitions = repetitions + 1
    else:
        new_repetitions = 0
        new_interval = 1

    new_ease_factor = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ease_factor = max(new_ease_factor, 1.3)

    return SM2Result(ease_factor=new_ease_factor, interval_days=new_interval, repetitions=new_repetitions)


def sync_srs_state(conn: sqlite3.Connection, repertoire: Optional[str] = None) -> int:
    """Create an srs_state row for every approved, non-root position missing one.

    Root positions (move_san IS NULL) have no move to drill, so they're
    excluded. Idempotent — safe to call before every drill session.
    Returns the number of rows created.
    """
    query = """
        SELECT rp.id FROM repertoire_positions rp
        LEFT JOIN srs_state srs ON srs.position_id = rp.id
        WHERE rp.status = 'approved' AND rp.move_san IS NOT NULL AND srs.position_id IS NULL
    """
    params: list[str] = []
    if repertoire:
        query += " AND rp.repertoire = ?"
        params.append(repertoire)

    missing_ids = [row["id"] for row in conn.execute(query, params).fetchall()]
    for position_id in missing_ids:
        conn.execute("INSERT INTO srs_state (position_id) VALUES (?)", (position_id,))
    conn.commit()
    return len(missing_ids)


def get_due_positions(
    conn: sqlite3.Connection, repertoire: Optional[str] = None, as_of: Optional[str] = None
) -> list[sqlite3.Row]:
    as_of = as_of or _now_str()
    query = """
        SELECT rp.*, srs.ease_factor, srs.interval_days, srs.repetitions, srs.due_at
        FROM repertoire_positions rp
        JOIN srs_state srs ON srs.position_id = rp.id
        WHERE rp.status = 'approved' AND srs.due_at <= ?
    """
    params: list[str] = [as_of]
    if repertoire:
        query += " AND rp.repertoire = ?"
        params.append(repertoire)
    query += " ORDER BY srs.due_at"
    return conn.execute(query, params).fetchall()


def board_before_move(conn: sqlite3.Connection, position_row: sqlite3.Row) -> chess.Board:
    """Reconstruct the board as it was before position_row's move was played."""
    parent = conn.execute(
        "SELECT epd FROM repertoire_positions WHERE id = ?", (position_row["parent_id"],)
    ).fetchone()
    board = chess.Board()
    board.set_epd(parent["epd"])
    return board


def check_answer(board: chess.Board, expected_uci: str, user_input: str) -> bool:
    """True if user_input (SAN or UCI) resolves to the expected move on board."""
    user_input = user_input.strip()
    try:
        move = board.parse_san(user_input)
    except ValueError:
        try:
            move = chess.Move.from_uci(user_input.lower())
        except ValueError:
            return False
    return move.uci() == expected_uci


def grade_review(conn: sqlite3.Connection, position_id: int, quality: int, correct: bool) -> SM2Result:
    row = conn.execute(
        "SELECT ease_factor, interval_days, repetitions FROM srs_state WHERE position_id = ?",
        (position_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"no srs_state for position {position_id}")

    result = sm2(quality, row["ease_factor"], row["interval_days"], row["repetitions"])
    due_at = (datetime.now(timezone.utc) + timedelta(days=result.interval_days)).strftime(TIMESTAMP_FORMAT)
    reviewed_at = _now_str()

    conn.execute(
        """
        UPDATE srs_state
        SET ease_factor = ?, interval_days = ?, repetitions = ?, due_at = ?, last_reviewed_at = ?
        WHERE position_id = ?
        """,
        (result.ease_factor, result.interval_days, result.repetitions, due_at, reviewed_at, position_id),
    )
    conn.execute(
        """
        INSERT INTO review_history
            (position_id, reviewed_at, correct, grade, ease_factor_after, interval_days_after, repetitions_after)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (position_id, reviewed_at, 1 if correct else 0, quality, result.ease_factor, result.interval_days, result.repetitions),
    )
    conn.commit()
    return result
