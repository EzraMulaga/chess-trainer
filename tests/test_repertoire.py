import shutil
import sqlite3

import chess
import pytest

from chess_trainer.db import init_db
from chess_trainer.repertoire import (
    CandidateConfig,
    generate_candidates,
    import_pgn,
    line_to_root,
    list_pending,
    set_status,
)

LONDON_PGN = "1. d4 d5 2. Bf4 Nf6 *"
STARTPOS_EPD = chess.Board().epd()


@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def test_import_pgn_chains_positions_and_approves(conn):
    ids = import_pgn(conn, LONDON_PGN, "white_london")

    assert len(ids) == 5  # root + d4, d5, Bf4, Nf6
    rows = {
        row["id"]: row
        for row in conn.execute("SELECT * FROM repertoire_positions").fetchall()
    }
    assert set(rows) == set(ids)

    root = rows[ids[0]]
    assert root["parent_id"] is None
    assert root["epd"] == STARTPOS_EPD
    assert root["ply"] == 0

    for row in rows.values():
        assert row["status"] == "approved"
        assert row["source"] == "pgn_import"
        assert row["repertoire"] == "white_london"

    # chain is correctly linked parent -> child in move order
    for expected_parent, position_id in zip(ids, ids[1:]):
        assert rows[position_id]["parent_id"] == expected_parent

    moves = [rows[i]["move_san"] for i in ids[1:]]
    assert moves == ["d4", "d5", "Bf4", "Nf6"]


def test_import_pgn_rejects_unparseable_text(conn):
    with pytest.raises(ValueError):
        import_pgn(conn, "", "white_london")


def test_list_pending_set_status_and_line_to_root(conn):
    ids = import_pgn(conn, LONDON_PGN, "white_london")
    root_id = ids[0]

    # manually insert a pending candidate under the root, as
    # generate_candidates would
    cur = conn.execute(
        """
        INSERT INTO repertoire_positions
            (epd, parent_id, move_san, move_uci, ply, repertoire, source, status)
        VALUES ('some-epd', ?, 'Nf3', 'g1f3', 1, 'white_london', 'engine_generated', 'pending')
        """,
        (root_id,),
    )
    pending_id = cur.lastrowid
    conn.commit()

    pending = list_pending(conn, "white_london")
    assert [row["id"] for row in pending] == [pending_id]

    chain = line_to_root(conn, pending_id)
    assert [row["id"] for row in chain] == [root_id, pending_id]

    set_status(conn, pending_id, "approved")
    assert list_pending(conn, "white_london") == []
    assert (
        conn.execute(
            "SELECT status FROM repertoire_positions WHERE id = ?", (pending_id,)
        ).fetchone()["status"]
        == "approved"
    )


def test_set_status_rejects_invalid_value(conn):
    with pytest.raises(ValueError):
        set_status(conn, 1, "maybe")


STOCKFISH_PATH = shutil.which("stockfish")


@pytest.mark.skipif(STOCKFISH_PATH is None, reason="stockfish binary not on PATH")
def test_generate_candidates_expands_and_prunes(conn):
    config = CandidateConfig(max_ply=2, multipv=2, eval_drop_cp=50, search_depth=6, max_candidates=10)
    ids = generate_candidates(
        conn, STOCKFISH_PATH, chess.STARTING_FEN, "white_london", config
    )

    assert len(ids) > 1  # seed plus at least one candidate
    assert len(ids) <= config.max_candidates

    rows = {
        row["id"]: row
        for row in conn.execute("SELECT * FROM repertoire_positions").fetchall()
    }
    seed = rows[ids[0]]
    assert seed["parent_id"] is None
    assert seed["status"] == "approved"
    assert seed["epd"] == STARTPOS_EPD

    for position_id in ids[1:]:
        row = rows[position_id]
        assert row["status"] == "pending"
        assert row["source"] == "engine_generated"
        assert row["parent_id"] in rows
        assert row["ply"] <= config.max_ply
