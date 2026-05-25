CREATE TABLE channels (
    id INTEGER NOT NULL PRIMARY KEY,
    name VARCHAR(255),
    channel_id VARCHAR(128) UNIQUE,
    url VARCHAR(1024) NOT NULL UNIQUE,
    rss_url VARCHAR(1024),
    active BOOLEAN NOT NULL DEFAULT 1,
    last_checked_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE videos (
    id INTEGER NOT NULL PRIMARY KEY,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    youtube_video_id VARCHAR(64) NOT NULL UNIQUE,
    url VARCHAR(1024) NOT NULL UNIQUE,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    published_at DATETIME,
    duration_seconds FLOAT,
    status VARCHAR(64) NOT NULL DEFAULT 'discovered',
    downloaded_path VARCHAR(1024),
    audio_path VARCHAR(1024),
    transcript_path VARCHAR(1024),
    thumbnail_path VARCHAR(1024),
    metadata_json JSON,
    error TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE clips (
    id INTEGER NOT NULL PRIMARY KEY,
    video_id INTEGER NOT NULL REFERENCES videos(id),
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    viral_score FLOAT NOT NULL,
    reason TEXT,
    title VARCHAR(120),
    description TEXT,
    hashtags JSON,
    hook_text VARCHAR(140),
    clip_path VARCHAR(1024),
    subtitle_path VARCHAR(1024),
    status VARCHAR(64) NOT NULL DEFAULT 'detected',
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE uploads (
    id INTEGER NOT NULL PRIMARY KEY,
    clip_id INTEGER NOT NULL REFERENCES clips(id),
    youtube_video_id VARCHAR(64),
    status VARCHAR(64) NOT NULL DEFAULT 'queued',
    privacy_status VARCHAR(32) NOT NULL DEFAULT 'private',
    scheduled_for DATETIME,
    uploaded_at DATETIME,
    error TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE analytics (
    id INTEGER NOT NULL PRIMARY KEY,
    clip_id INTEGER NOT NULL REFERENCES clips(id),
    upload_id INTEGER REFERENCES uploads(id),
    views INTEGER NOT NULL DEFAULT 0,
    likes INTEGER NOT NULL DEFAULT 0,
    comments INTEGER NOT NULL DEFAULT 0,
    ctr FLOAT,
    retention_avg FLOAT,
    captured_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_videos_channel_status ON videos(channel_id, status);
CREATE INDEX ix_clips_video_score ON clips(video_id, viral_score);
CREATE INDEX ix_uploads_status_scheduled ON uploads(status, scheduled_for);
CREATE INDEX ix_analytics_clip_captured ON analytics(clip_id, captured_at);

