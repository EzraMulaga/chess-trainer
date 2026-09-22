import shutil
import sqlite3

import chess
import pytest

from chess_trainer.db import init_db
from chess_trainer.review import ReviewConfig, _maybe_upgrade_to_brilliant, classify, review_game

STOCKFISH_PATH = shutil.which("stockfish")

# 3. Qxe5?? hangs the queen to Nxe5 — an unambiguous blunder for the test.
BLUNDER_PGN = """[Event "Test"]
[White "A"]
[Black "B"]
[Result "*"]

1. e4 e5 2. Qh5 Nc6 3. Qxe5 Nxe5 *
"""


@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def test_classify_bands():
    config = ReviewConfig()
    assert classify(0, config) == "best"
    assert classify(config.best_cp, config) == "best"
    assert classify(config.best_cp + 1, config) == "excellent"
    assert classify(config.excellent_cp, config) == "excellent"
    assert classify(config.excellent_cp + 1, config) == "inaccuracy"
    assert classify(config.inaccuracy_cp, config) == "inaccuracy"
    assert classify(config.inaccuracy_cp + 1, config) == "mistake"
    assert classify(config.mistake_cp, config) == "mistake"
    assert classify(config.mistake_cp + 1, config) == "blunder"


def test_brilliant_heuristic_flags_genuine_sacrifice():
    # White: Qd1, Ke1. Black: Rd8, Ke8. Qd1-d5 hangs the queen to Rxd5,
    # but we pass classification='best'/small loss directly to isolate the
    # material-swing logic from real engine evaluation.
    board_before = chess.Board("3rk3/8/8/8/8/8/8/3QK3 w - - 0 1")
    move = chess.Move.from_uci("d1d5")
    board_after = board_before.copy()
    board_after.push(move)
    info_after = {"pv": [chess.Move.from_uci("d8d5")]}  # Black's best reply: Rxd5

    result = _maybe_upgrade_to_brilliant(
        board_before, move, board_after, "best", 10, info_after, ReviewConfig()
    )
    assert result == "brilliant"


def test_brilliant_heuristic_ignores_small_sacrifice():
    board_before = chess.Board("3rk3/8/8/8/8/8/8/3QK3 w - - 0 1")
    move = chess.Move.from_uci("d1d5")
    board_after = board_before.copy()
    board_after.push(move)
    # No capturing reply available -> no material swing at all.
    info_after = {"pv": [chess.Move.from_uci("e8e7")]}

    result = _maybe_upgrade_to_brilliant(
        board_before, move, board_after, "best", 10, info_after, ReviewConfig()
    )
    assert result == "best"


def test_brilliant_heuristic_requires_sound_classification():
    board_before = chess.Board("3rk3/8/8/8/8/8/8/3QK3 w - - 0 1")
    move = chess.Move.from_uci("d1d5")
    board_after = board_before.copy()
    board_after.push(move)
    info_after = {"pv": [chess.Move.from_uci("d8d5")]}

    result = _maybe_upgrade_to_brilliant(
        board_before, move, board_after, "mistake", 150, info_after, ReviewConfig()
    )
    assert result == "mistake"


def test_brilliant_heuristic_skips_forced_moves():
    # White king in check with the only legal move being to capture the checker.
    board_before = chess.Board("k7/8/8/8/8/8/6q1/7K w - - 0 1")
    assert board_before.legal_moves.count() == 1
    move = next(iter(board_before.legal_moves))
    board_after = board_before.copy()
    board_after.push(move)
    info_after = {"pv": []}

    result = _maybe_upgrade_to_brilliant(
        board_before, move, board_after, "best", 5, info_after, ReviewConfig()
    )
    assert result == "best"


@pytest.mark.skipif(STOCKFISH_PATH is None, reason="stockfish binary not on PATH")
def test_review_game_persists_moves_and_flags_the_blunder(conn):
    game_id, reviews = review_game(
        conn, STOCKFISH_PATH, BLUNDER_PGN, ReviewConfig(search_depth=10)
    )

    assert len(reviews) == 6
    assert reviews[4].move_san == "Qxe5+"
    assert reviews[4].classification == "blunder"

    game_row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    assert game_row["white"] == "A"
    assert game_row["black"] == "B"
    assert game_row["pgn"] == BLUNDER_PGN

    move_rows = conn.execute(
        "SELECT * FROM game_moves WHERE game_id = ? ORDER BY ply", (game_id,)
    ).fetchall()
    assert len(move_rows) == 6
    assert move_rows[4]["classification"] == "blunder"
    assert move_rows[4]["move_san"] == "Qxe5+"
