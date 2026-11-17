-- Rally Ledger database (Cloudflare D1 / SQLite)

-- The current feed, one row, overwritten every minute.
CREATE TABLE IF NOT EXISTS snapshot (
  id      INTEGER PRIMARY KEY CHECK (id = 1),
  data    TEXT NOT NULL,
  updated TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
  id      TEXT PRIMARY KEY,            -- your own id, e.g. "jannik-sinner"
  name    TEXT NOT NULL,
  country TEXT,
  aliases TEXT NOT NULL DEFAULT '[]',  -- JSON list of other spellings from other feeds
  updated TEXT
);

CREATE TABLE IF NOT EXISTS events (
  id      TEXT PRIMARY KEY,            -- source-prefixed, e.g. "espn:12345"
  name    TEXT NOT NULL,
  venue   TEXT,
  start   TEXT,                        -- UTC
  end     TEXT,                        -- UTC
  updated TEXT
);

-- Finished matches only. Live matches stay in the snapshot.
CREATE TABLE IF NOT EXISTS matches (
  id       TEXT PRIMARY KEY,           -- source-prefixed
  event_id TEXT NOT NULL,
  draw     TEXT,
  round    TEXT,
  court    TEXT,
  start    TEXT,                       -- UTC
  state    TEXT NOT NULL,              -- finished | retired | walkover
  best_of  INTEGER,
  p1_id    TEXT,
  p2_id    TEXT,
  winner   INTEGER,                    -- 0 or 1, index into the players
  score    TEXT,                       -- "6-4 6-7(5) 7-5"
  seconds  INTEGER,                    -- match duration, null if not observed live
  data     TEXT NOT NULL,              -- the full match in Rally Ledger JSON format
  updated  TEXT
);
CREATE INDEX IF NOT EXISTS matches_event ON matches (event_id);
CREATE INDEX IF NOT EXISTS matches_p1 ON matches (p1_id);
CREATE INDEX IF NOT EXISTS matches_p2 ON matches (p2_id);

-- Unused until a point-by-point feed is connected.
CREATE TABLE IF NOT EXISTS points (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  match_id  TEXT NOT NULL,
  n         INTEGER NOT NULL,          -- point number within the match
  set_no    INTEGER,
  game_no   INTEGER,
  server    INTEGER,                   -- 0 or 1
  winner    INTEGER,                   -- 0 or 1
  serve     INTEGER,                   -- 1 = first serve, 2 = second serve
  ending    TEXT,                      -- ace | double_fault | winner | unforced_error | forced_error
  score     TEXT,                      -- game score after the point
  at        TEXT,                      -- UTC
  UNIQUE (match_id, n)
);
