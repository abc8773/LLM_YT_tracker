PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_channel_id TEXT UNIQUE,
    name TEXT NOT NULL,
    handle TEXT,
    url TEXT NOT NULL UNIQUE,
    description TEXT,
    last_checked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    youtube_video_id TEXT NOT NULL UNIQUE,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    published_at TEXT,
    url TEXT NOT NULL,
    duration_seconds INTEGER,
    thumbnail_url TEXT,
    transcript_status TEXT NOT NULL DEFAULT 'pending',
    analysis_status TEXT NOT NULL DEFAULT 'pending',
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL UNIQUE REFERENCES videos(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    language TEXT,
    raw_text TEXT NOT NULL,
    cleaned_text TEXT NOT NULL,
    generated_with TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL UNIQUE REFERENCES videos(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    summary TEXT NOT NULL,
    speakers_json TEXT NOT NULL,
    topics_json TEXT NOT NULL,
    keywords_json TEXT NOT NULL,
    themes_json TEXT NOT NULL,
    confidence REAL,
    raw_response TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    details_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_videos_channel_id ON videos(channel_id);
CREATE INDEX IF NOT EXISTS idx_videos_published_at ON videos(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_videos_transcript_status ON videos(transcript_status);
CREATE INDEX IF NOT EXISTS idx_videos_analysis_status ON videos(analysis_status);
