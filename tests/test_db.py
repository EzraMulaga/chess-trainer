import sqlite3

import pytest

from chess_trainer.db import init_db

STARTPOS_EPD = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"


@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def test_init_db_creates_all_tables(conn):
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "repertoire_positions",
        "srs_state",
        "review_history",
        "games",
        "game_moves",
    } <= tables


def test_insert_and_read_one_row_per_table(conn):
    cur = conn.execute(
        """
        INSERT INTO repertoire_positions
            (epd, parent_id, move_san, move_uci, ply, repertoire, source, status)
        VALUES (?, NULL, NULL, NULL, 0, 'white_london', 'pgn_import', 'approved')
        """,
        (STARTPOS_EPD,),
    )
    position_id = cur.lastrowid

    conn.execute(
        """
        INSERT INTO srs_state (position_id, ease_factor, interval_days, repetitions)
        VALUES (?, 2.5, 0, 0)
        """,
        (position_id,),
    )

    conn.execute(
        """
        INSERT INTO review_history
            (position_id, correct, grade, ease_factor_after, interval_days_after, repetitions_after)
        VALUES (?, 1, 4, 2.6, 1, 1)
        """,
        (position_id,),
    )

    cur = conn.execute(
        "INSERT INTO games (pgn, white, black, result) VALUES (?, ?, ?, ?)",
        ("1. e4 e6 *", "Alice", "Bob", "*"),
    )
    game_id = cur.lastrowid

    conn.execute(
        """
        INSERT INTO game_moves (game_id, ply, move_san, move_uci, classification)
        VALUES (?, 1, 'e4', 'e2e4', 'best')
        """,
        (game_id,),
    )
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM repertoire_positions").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM srs_state").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM review_history").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM game_moves").fetchone()[0] == 1


def test_deleting_position_cascades_srs_and_review_history(conn):
    cur = conn.execute(
        """
        INSERT INTO repertoire_positions
            (epd, parent_id, move_san, move_uci, ply, repertoire, source, status)
        VALUES (?, NULL, NULL, NULL, 0, 'black_caro_kann', 'pgn_import', 'approved')
        """,
        (STARTPOS_EPD,),
    )
    position_id = cur.lastrowid
    conn.execute("INSERT INTO srs_state (position_id) VALUES (?)", (position_id,))
    conn.execute(
        """
        INSERT INTO review_history
            (position_id, correct, grade, ease_factor_after, interval_days_after, repetitions_after)
        VALUES (?, 1, 4, 2.6, 1, 1)
        """,
        (position_id,),
    )

    conn.execute("DELETE FROM repertoire_positions WHERE id = ?", (position_id,))

    assert conn.execute("SELECT COUNT(*) FROM srs_state").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM review_history").fetchone()[0] == 0


def test_invalid_classification_rejected(conn):
    game_id = conn.execute(
        "INSERT INTO games (pgn) VALUES ('*')"
    ).lastrowid
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO game_moves (game_id, ply, move_san, move_uci, classification)
            VALUES (?, 1, 'e4', 'e2e4', 'amazing')
            """,
            (game_id,),
        )
