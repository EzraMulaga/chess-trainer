-- Phase 1 schema. Position identity uses EPD (FEN without halfmove/fullmove
-- counters) so the same opening position reached at different points in a
-- line still compares equal.
--
-- eval_cp / eval_mate (on repertoire_positions and game_moves) are always
-- from White's point of view, matching python-chess's score.white()
-- convention. eval_mate holds moves-to-mate when the score is forced mate
-- (positive = White mates, negative = White gets mated); eval_cp is NULL
-- in that case.

CREATE TABLE IF NOT EXISTS repertoire_positions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    epd           TEXT NOT NULL,
    parent_id     INTEGER REFERENCES repertoire_positions(id) ON DELETE CASCADE,
    move_san      TEXT,
    move_uci      TEXT,
    ply           INTEGER NOT NULL,
    repertoire    TEXT NOT NULL,
    source        TEXT NOT NULL CHECK (source IN ('pgn_import', 'engine_generated')),
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    eval_cp       INTEGER,
    eval_mate     INTEGER,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_repertoire_positions_parent ON repertoire_positions(parent_id);
CREATE INDEX IF NOT EXISTS idx_repertoire_positions_repertoire_status ON repertoire_positions(repertoire, status);
CREATE INDEX IF NOT EXISTS idx_repertoire_positions_epd ON repertoire_positions(epd);

CREATE TABLE IF NOT EXISTS srs_state (
    position_id       INTEGER PRIMARY KEY REFERENCES repertoire_positions(id) ON DELETE CASCADE,
    ease_factor       REAL NOT NULL DEFAULT 2.5,
    interval_days     INTEGER NOT NULL DEFAULT 0,
    repetitions       INTEGER NOT NULL DEFAULT 0,
    due_at            TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_reviewed_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_srs_state_due_at ON srs_state(due_at);

CREATE TABLE IF NOT EXISTS review_history (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id           INTEGER NOT NULL REFERENCES repertoire_positions(id) ON DELETE CASCADE,
    reviewed_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    correct               INTEGER NOT NULL CHECK (correct IN (0, 1)),
    grade                 INTEGER NOT NULL CHECK (grade BETWEEN 0 AND 5),
    ease_factor_after     REAL NOT NULL,
    interval_days_after   INTEGER NOT NULL,
    repetitions_after     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_review_history_position ON review_history(position_id);

CREATE TABLE IF NOT EXISTS games (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    pgn           TEXT NOT NULL,
    white         TEXT,
    black         TEXT,
    result        TEXT,
    played_at     TEXT,
    source        TEXT NOT NULL DEFAULT 'manual_paste',
    imported_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS game_moves (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id           INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    ply               INTEGER NOT NULL,
    move_san          TEXT NOT NULL,
    move_uci          TEXT NOT NULL,
    eval_before_cp    INTEGER,
    eval_before_mate  INTEGER,
    eval_after_cp     INTEGER,
    eval_after_mate   INTEGER,
    eval_delta_cp     INTEGER,
    classification    TEXT NOT NULL CHECK (classification IN
                          ('best', 'excellent', 'inaccuracy', 'mistake', 'blunder', 'brilliant')),
    UNIQUE (game_id, ply)
);

CREATE INDEX IF NOT EXISTS idx_game_moves_game ON game_moves(game_id);
