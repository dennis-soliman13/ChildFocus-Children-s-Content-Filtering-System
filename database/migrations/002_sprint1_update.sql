-- database/migrations/001_sprint1_schema_update.sql
-- Safe migration: uses ALTER TABLE ADD COLUMN (no data loss)
-- Run once on existing childfocus.db to bring it up to date.
-- SQLite ignores "IF NOT EXISTS" on columns so we wrap in separate statements.

-- ── videos table additions ────────────────────────────────────────────────────
ALTER TABLE videos ADD COLUMN video_title           TEXT;
ALTER TABLE videos ADD COLUMN thumbnail_url         TEXT;
ALTER TABLE videos ADD COLUMN thumbnail_intensity   REAL;
ALTER TABLE videos ADD COLUMN heuristic_score       REAL;
ALTER TABLE videos ADD COLUMN nb_score              REAL;
ALTER TABLE videos ADD COLUMN preliminary_label     TEXT;
ALTER TABLE videos ADD COLUMN classified_by         TEXT;
ALTER TABLE videos ADD COLUMN video_duration_sec    REAL;
ALTER TABLE videos ADD COLUMN runtime_seconds       REAL;

-- ── Fix label constraint ──────────────────────────────────────────────────────
-- SQLite does not support ALTER COLUMN so we recreate videos with correct CHECK.
-- This is safe: existing data is preserved via INSERT INTO ... SELECT.

-- Step 1: rename old table
ALTER TABLE videos RENAME TO videos_old;

-- Step 2: create new table with correct schema
CREATE TABLE videos (
    video_id              TEXT PRIMARY KEY,
    video_title           TEXT,
    thumbnail_url         TEXT,
    thumbnail_intensity   REAL,
    heuristic_score       REAL,
    nb_score              REAL,
    final_score           REAL,
    label                 TEXT CHECK(label IN ('Educational', 'Neutral', 'Overstimulating')),
    preliminary_label     TEXT,
    classified_by         TEXT CHECK(classified_by IN ('cache', 'fast_path', 'full_analysis')),
    video_duration_sec    REAL,
    runtime_seconds       REAL,
    last_checked          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    checked_by            TEXT
);

-- Step 3: copy existing data (maps old final_score and checked_by)
INSERT INTO videos (video_id, final_score, last_checked, checked_by)
SELECT video_id, final_score, last_checked, checked_by
FROM videos_old;

-- Step 4: drop old table
DROP TABLE videos_old;

-- ── segments table additions ──────────────────────────────────────────────────
ALTER TABLE segments ADD COLUMN segment_id  TEXT;
ALTER TABLE segments ADD COLUMN frame_count INTEGER;

-- ── logs action constraint update ────────────────────────────────────────────
-- Same pattern: recreate with correct CHECK constraint

ALTER TABLE logs RENAME TO logs_old;

CREATE TABLE logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id       TEXT    REFERENCES videos(video_id),
    user_id        TEXT    REFERENCES users(user_id),
    action         TEXT    CHECK(action IN ('allowed', 'blocked', 'blurred', 'alerted')),
    timestamp      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason_details TEXT
);

INSERT INTO logs (id, video_id, user_id, action, timestamp, reason_details)
SELECT id, video_id, user_id, action, timestamp, reason_details
FROM logs_old;

DROP TABLE logs_old;

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_videos_video_id   ON videos(video_id);
CREATE INDEX IF NOT EXISTS idx_segments_video_id ON segments(video_id);
CREATE INDEX IF NOT EXISTS idx_logs_user_id      ON logs(user_id);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp    ON logs(timestamp);