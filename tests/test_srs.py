import sqlite3

import chess
import pytest

from chess_trainer.db import init_db
from chess_trainer.repertoire import import_pgn
from chess_trainer.srs import (
    board_before_move,
    check_answer,
    get_due_positions,
    grade_review,
    sm2,
    sync_srs_state,
)

LONDON_PGN = "1. d4 d5 2. Bf4 *"


# --- SM-2 reference sequences -------------------------------------------------


def test_sm2_first_successful_review():
    result = sm2(quality=5, ease_factor=2.5, interval_days=0, repetitions=0)
    assert result.interval_days == 1
    assert result.repetitions == 1
    assert result.ease_factor == pytest.approx(2.6)


def test_sm2_second_successful_review():
    result = sm2(quality=5, ease_factor=2.6, interval_days=1, repetitions=1)
    assert result.interval_days == 6
    assert result.repetitions == 2
    assert result.ease_factor == pytest.approx(2.7)


def test_sm2_third_successful_review():
    result = sm2(quality=5, ease_factor=2.7, interval_days=6, repetitions=2)
    assert result.interval_days == round(6 * 2.7)  # 16
    assert result.repetitions == 3
    assert result.ease_factor == pytest.approx(2.8)


def test_sm2_boundary_pass_quality_three():
    result = sm2(quality=3, ease_factor=2.5, interval_days=6, repetitions=2)
    assert result.interval_days == round(6 * 2.5)  # 15
    assert result.repetitions == 3
    assert result.ease_factor == pytest.approx(2.36)


def test_sm2_failing_grade_resets_repetitions_and_interval():
    result = sm2(quality=0, ease_factor=2.5, interval_days=16, repetitions=3)
    assert result.interval_days == 1
    assert result.repetitions == 0
    assert result.ease_factor == pytest.approx(1.7)


def test_sm2_ease_factor_floors_at_1_3():
    result = sm2(quality=0, ease_factor=1.3, interval_days=1, repetitions=0)
    assert result.ease_factor == pytest.approx(1.3)
    assert result.interval_days == 1
    assert result.repetitions == 0


@pytest.mark.parametrize("quality", [-1, 6])
def test_sm2_rejects_out_of_range_quality(quality):
    with pytest.raises(ValueError):
        sm2(quality=quality, ease_factor=2.5, interval_days=0, repetitions=0)


# --- drill data access ---------------------------------------------------------


@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def test_sync_srs_state_skips_root_and_is_idempotent(conn):
    ids = import_pgn(conn, LONDON_PGN, "white_london")  # root, d4, d5, Bf4

    created = sync_srs_state(conn, "white_london")
    assert created == 3  # root excluded (move_san IS NULL)

    rows = conn.execute("SELECT position_id FROM srs_state").fetchall()
    assert {r["position_id"] for r in rows} == set(ids[1:])

    again = sync_srs_state(conn, "white_london")
    assert again == 0


def test_get_due_positions_respects_due_at_and_repertoire(conn):
    ids = import_pgn(conn, LONDON_PGN, "white_london")
    sync_srs_state(conn, "white_london")

    due_now = get_due_positions(conn, "white_london")
    assert {r["id"] for r in due_now} == set(ids[1:])

    future = "2999-01-01 00:00:00"
    conn.execute("UPDATE srs_state SET due_at = ? WHERE position_id = ?", (future, ids[1]))
    conn.commit()

    due_now = get_due_positions(conn, "white_london")
    assert ids[1] not in {r["id"] for r in due_now}
    assert ids[2] in {r["id"] for r in due_now}

    assert get_due_positions(conn, "black_caro_kann") == []


def test_board_before_move_and_check_answer(conn):
    ids = import_pgn(conn, LONDON_PGN, "white_london")
    d4_row = conn.execute("SELECT * FROM repertoire_positions WHERE id = ?", (ids[1],)).fetchone()

    board = board_before_move(conn, d4_row)
    assert board == chess.Board()  # root position

    assert check_answer(board, d4_row["move_uci"], "d4")
    assert check_answer(board, d4_row["move_uci"], "d2d4")
    assert not check_answer(board, d4_row["move_uci"], "e4")
    assert not check_answer(board, d4_row["move_uci"], "not a move")


def test_grade_review_updates_srs_state_and_logs_history(conn):
    ids = import_pgn(conn, LONDON_PGN, "white_london")
    sync_srs_state(conn, "white_london")
    position_id = ids[1]

    result = grade_review(conn, position_id, quality=5, correct=True)
    assert result.repetitions == 1
    assert result.interval_days == 1

    srs_row = conn.execute(
        "SELECT * FROM srs_state WHERE position_id = ?", (position_id,)
    ).fetchone()
    assert srs_row["repetitions"] == 1
    assert srs_row["last_reviewed_at"] is not None

    history_row = conn.execute(
        "SELECT * FROM review_history WHERE position_id = ?", (position_id,)
    ).fetchone()
    assert history_row["correct"] == 1
    assert history_row["grade"] == 5


def test_grade_review_raises_without_srs_state(conn):
    ids = import_pgn(conn, LONDON_PGN, "white_london")
    with pytest.raises(ValueError):
        grade_review(conn, ids[1], quality=5, correct=True)
