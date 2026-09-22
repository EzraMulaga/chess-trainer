import shutil
import sqlite3

import pytest
from fastapi.testclient import TestClient

from chess_trainer.api import app, get_db, require_engine_path
from chess_trainer.db import init_db

STOCKFISH_PATH = shutil.which("stockfish")

LONDON_PGN = "1. d4 d5 2. Bf4 *"

BLUNDER_PGN = """[Event "Test"]
[White "A"]
[Black "B"]
[Result "*"]

1. e4 e5 2. Qh5 Nc6 3. Qxe5 Nxe5 *
"""


@pytest.fixture
def client():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    def override_get_db():
        yield conn

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        conn.close()


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_import_pgn_then_list_pending_is_empty(client):
    resp = client.post("/repertoire/import-pgn", json={"pgn": LONDON_PGN, "repertoire": "white_london"})
    assert resp.status_code == 200
    ids = resp.json()["position_ids"]
    assert len(ids) == 4  # root, d4, d5, Bf4

    pending = client.get("/repertoire/pending", params={"repertoire": "white_london"})
    assert pending.status_code == 200
    assert pending.json() == []  # PGN import auto-approves


def test_import_pgn_rejects_bad_pgn(client):
    resp = client.post("/repertoire/import-pgn", json={"pgn": "", "repertoire": "white_london"})
    assert resp.status_code == 400


def test_set_status_roundtrip_and_line_to_root(client):
    ids = client.post(
        "/repertoire/import-pgn", json={"pgn": LONDON_PGN, "repertoire": "white_london"}
    ).json()["position_ids"]
    root_id, leaf_id = ids[0], ids[-1]

    resp = client.post(f"/repertoire/positions/{leaf_id}/status", json={"status": "rejected"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    resp = client.post(f"/repertoire/positions/{leaf_id}/status", json={"status": "not-a-status"})
    assert resp.status_code == 400

    resp = client.get(f"/repertoire/positions/{leaf_id}/line")
    assert resp.status_code == 200
    line = resp.json()
    assert [p["id"] for p in line] == ids
    assert line[0]["id"] == root_id

    resp = client.get("/repertoire/positions/99999/line")
    assert resp.status_code == 404


def test_drill_due_and_answer_flow(client):
    client.post("/repertoire/import-pgn", json={"pgn": LONDON_PGN, "repertoire": "white_london"})

    due = client.get("/drill/due", params={"repertoire": "white_london"})
    assert due.status_code == 200
    due_items = due.json()
    assert len(due_items) == 3  # d4, d5, Bf4 (root has no move to drill)

    first = due_items[0]
    assert first["move_san"] == "d4"
    assert first["fen"].startswith("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR")

    resp = client.post(f"/drill/positions/{first['id']}/answer", json={"move": "d4", "quality": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["correct"] is True
    assert body["interval_days"] == 1
    assert body["ease_factor"] == pytest.approx(2.6)

    resp = client.post(f"/drill/positions/{999999}/answer", json={"move": "d4"})
    assert resp.status_code == 404


def test_answer_wrong_move_grades_zero(client):
    client.post("/repertoire/import-pgn", json={"pgn": LONDON_PGN, "repertoire": "white_london"})
    due_items = client.get("/drill/due", params={"repertoire": "white_london"}).json()
    first = due_items[0]

    resp = client.post(f"/drill/positions/{first['id']}/answer", json={"move": "e4"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["correct"] is False
    assert body["correct_move_san"] == "d4"
    assert body["ease_factor"] == pytest.approx(1.7)


def test_generate_candidates_without_engine_returns_503(client):
    app.dependency_overrides[require_engine_path] = lambda: (_ for _ in ()).throw(
        __import__("fastapi").HTTPException(status_code=503, detail="Stockfish not available on the server")
    )
    try:
        resp = client.post(
            "/repertoire/generate-candidates",
            json={"seed_fen": "startpos", "repertoire": "white_london"},
        )
        assert resp.status_code == 503
    finally:
        del app.dependency_overrides[require_engine_path]


@pytest.mark.skipif(STOCKFISH_PATH is None, reason="stockfish binary not on PATH")
def test_review_game_endpoint_and_fetch(client):
    resp = client.post("/games/review", json={"pgn": BLUNDER_PGN, "search_depth": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["moves"]) == 6
    assert body["moves"][4]["move_san"] == "Qxe5+"
    assert body["moves"][4]["classification"] == "blunder"

    game_id = body["game_id"]
    fetched = client.get(f"/games/{game_id}")
    assert fetched.status_code == 200
    fetched_body = fetched.json()
    assert fetched_body["white"] == "A"
    assert len(fetched_body["moves"]) == 6

    assert client.get("/games/999999").status_code == 404


@pytest.mark.skipif(STOCKFISH_PATH is None, reason="stockfish binary not on PATH")
def test_generate_candidates_endpoint(client):
    resp = client.post(
        "/repertoire/generate-candidates",
        json={
            "seed_fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "repertoire": "white_london",
            "max_ply": 2,
            "multipv": 2,
            "search_depth": 6,
            "max_candidates": 6,
        },
    )
    assert resp.status_code == 200
    ids = resp.json()["position_ids"]
    assert len(ids) > 1

    pending = client.get("/repertoire/pending", params={"repertoire": "white_london"}).json()
    assert len(pending) == len(ids) - 1  # all but the seed
