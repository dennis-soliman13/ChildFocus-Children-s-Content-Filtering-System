-- database/schema.sql
-- ChildFocus: AI-Based Children's Content Filtering System
-- Updated: Aligned with frame_sampler.py output + manuscript labels + Sprint 2 NB fields

-- ── Videos ────────────────────────────────────────────────────────────────────
-- Central classification result per video.
-- Labels aligned with manuscript: Educational / Neutral / Overstimulating
-- 'Safe' and 'Uncertain' are internal fast-path labels, mapped before storing.

CREATE TABLE IF NOT EXISTS videos (
    video_id              TEXT PRIMARY KEY,
    video_title           TEXT,
    thumbnail_url         TEXT,
    thumbnail_intensity   REAL,

    -- Heuristic component (Sprint 1)
    heuristic_score       REAL,               -- aggregate Score_H (0.80*max_seg + 0.20*thumb)

    -- Naïve Bayes component (Sprint 2)
    nb_score              REAL,               -- Score_NB from metadata classifier

    -- Hybrid fusion output (Sprint 3)
    final_score           REAL,               -- Score_final = α*NB + (1-α)*H
    label                 TEXT CHECK(label IN ('Educational', 'Neutral', 'Overstimulating')),
    preliminary_label     TEXT,               -- fast-path result before full analysis

    -- Classification path taken
    classified_by         TEXT CHECK(classified_by IN (
                              'cache',        -- returned from DB instantly
                              'fast_path',    -- NB + thumbnail only (~1-2s)
                              'full_analysis' -- 3-segment heuristic (~15s)
                          )),

    -- Meta
    video_duration_sec    REAL,
    runtime_seconds       REAL,               -- how long classification took
    last_checked          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    checked_by            TEXT                -- user_id or 'system'
);

-- ── Segments ──────────────────────────────────────────────────────────────────
-- Per-segment heuristic features from frame_sampler.py.
-- One video → up to 3 segment rows (S1 begin / S2 mid / S3 end).

CREATE TABLE IF NOT EXISTS segments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id       TEXT    NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
    segment_id     TEXT    NOT NULL,   -- 'S1', 'S2', 'S3'
    offset_seconds INTEGER NOT NULL,
    length_seconds INTEGER NOT NULL,

    -- Heuristic features (manuscript Chapter 4 formulas)
    fcr            REAL,               -- Frame-Change Rate        [0,1]
    csv            REAL,               -- Color-Saturation Variance [0,1]
    att            REAL,               -- Audio Tempo Transitions   [0,1]
    score          REAL,               -- Score_H = 0.35*FCR + 0.25*CSV + 0.20*ATT

    frame_count    INTEGER            -- number of frames sampled
);

-- ── Users ─────────────────────────────────────────────────────────────────────
-- Parent accounts and their customized filtering settings.
-- parent_settings stored as JSON for flexibility (thresholds, alerts, screen-time).

CREATE TABLE IF NOT EXISTS users (
    user_id         TEXT PRIMARY KEY,
    parent_settings TEXT   -- JSON: { "block_threshold": 0.75, "alert_email": "...", "screen_time_limit": 60 }
);

-- ── Logs ──────────────────────────────────────────────────────────────────────
-- Audit trail of every action taken on a video for a user.
-- Supports parent dashboard and UAT reporting.

CREATE TABLE IF NOT EXISTS logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id       TEXT    REFERENCES videos(video_id),
    user_id        TEXT    REFERENCES users(user_id),
    action         TEXT    CHECK(action IN (
                       'allowed',   -- video passed filtering
                       'blocked',   -- video was hard-blocked
                       'blurred',   -- thumbnail blurred, warning shown
                       'alerted'    -- parent notification sent
                   )),
    timestamp      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason_details TEXT               -- JSON: { "score": 0.82, "label": "Overstimulating", ... }
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
-- Speed up the two most frequent lookups:
--   1. Cache check: SELECT * FROM videos WHERE video_id = ?
--   2. Log history: SELECT * FROM logs WHERE user_id = ? ORDER BY timestamp DESC

CREATE INDEX IF NOT EXISTS idx_videos_video_id   ON videos(video_id);
CREATE INDEX IF NOT EXISTS idx_segments_video_id ON segments(video_id);
CREATE INDEX IF NOT EXISTS idx_logs_user_id      ON logs(user_id);
CREATE INDEX IF NOT EXISTS idx_logs_timestamp    ON logs(timestamp);