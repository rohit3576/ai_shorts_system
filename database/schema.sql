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
    rights_review_id INTEGER REFERENCES rights_reviews(id),
    quality_gate_status VARCHAR(40),
    metadata_json JSON,
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
    average_view_duration_seconds FLOAT,
    average_view_percentage FLOAT,
    watch_time_minutes FLOAT,
    watch_percentage FLOAT,
    subscriber_gain INTEGER,
    shares INTEGER,
    impressions INTEGER,
    rewatch_rate FLOAT,
    snapshot_window_hours INTEGER,
    upload_age_hours FLOAT,
    metric_source VARCHAR(20) NOT NULL DEFAULT 'REAL',
    capture_status VARCHAR(40) NOT NULL DEFAULT 'captured',
    unavailable_metrics JSON,
    raw_json JSON,
    error TEXT,
    captured_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_videos_channel_status ON videos(channel_id, status);
CREATE INDEX ix_clips_video_score ON clips(video_id, viral_score);
CREATE INDEX ix_uploads_status_scheduled ON uploads(status, scheduled_for);
CREATE INDEX ix_analytics_clip_captured ON analytics(clip_id, captured_at);

CREATE TABLE review_decisions (
    id INTEGER NOT NULL PRIMARY KEY,
    clip_id INTEGER NOT NULL REFERENCES clips(id),
    action VARCHAR(40) NOT NULL,
    labels_json JSON,
    reason TEXT,
    reviewer VARCHAR(120),
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE rights_reviews (
    id INTEGER NOT NULL PRIMARY KEY,
    clip_id INTEGER NOT NULL REFERENCES clips(id),
    owned_content BOOLEAN NOT NULL DEFAULT 0,
    licensed_content BOOLEAN NOT NULL DEFAULT 0,
    commentary_added BOOLEAN NOT NULL DEFAULT 0,
    narration_added BOOLEAN NOT NULL DEFAULT 0,
    transformative_edit BOOLEAN NOT NULL DEFAULT 0,
    approved_for_upload BOOLEAN NOT NULL DEFAULT 0,
    originality_score FLOAT NOT NULL DEFAULT 0,
    policy_notes TEXT,
    reviewer VARCHAR(120),
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE quality_gate_results (
    id INTEGER NOT NULL PRIMARY KEY,
    clip_id INTEGER NOT NULL REFERENCES clips(id),
    upload_id INTEGER REFERENCES uploads(id),
    passed BOOLEAN NOT NULL DEFAULT 0,
    originality_score FLOAT NOT NULL DEFAULT 0,
    hook_quality FLOAT NOT NULL DEFAULT 0,
    subtitle_readability FLOAT NOT NULL DEFAULT 0,
    pacing_score FLOAT NOT NULL DEFAULT 0,
    dead_zone_risk FLOAT NOT NULL DEFAULT 0,
    render_quality FLOAT NOT NULL DEFAULT 0,
    review_approved BOOLEAN NOT NULL DEFAULT 0,
    reasons_json JSON,
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE negative_samples (
    id INTEGER NOT NULL PRIMARY KEY,
    clip_id INTEGER REFERENCES clips(id),
    video_id INTEGER REFERENCES videos(id),
    category VARCHAR(80) NOT NULL,
    reason TEXT,
    labels_json JSON,
    severity FLOAT NOT NULL DEFAULT 0,
    features_json JSON,
    source VARCHAR(80) NOT NULL DEFAULT 'system',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE channel_profiles (
    id INTEGER NOT NULL PRIMARY KEY,
    channel_id INTEGER NOT NULL UNIQUE REFERENCES channels(id),
    niche_type VARCHAR(80) NOT NULL DEFAULT 'general',
    target_audience VARCHAR(255),
    upload_style VARCHAR(80) NOT NULL DEFAULT 'curiosity clips',
    hook_style VARCHAR(80) NOT NULL DEFAULT 'curiosity gap',
    subtitle_style VARCHAR(80) NOT NULL DEFAULT 'tiktok punch captions',
    pacing_style VARCHAR(80) NOT NULL DEFAULT 'fast cut',
    target_duration_seconds INTEGER NOT NULL DEFAULT 38,
    upload_frequency_per_day INTEGER NOT NULL DEFAULT 2,
    schedule_json JSON,
    estimated_shorts_rpm FLOAT NOT NULL DEFAULT 0.06,
    active BOOLEAN NOT NULL DEFAULT 1,
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE source_feeds (
    id INTEGER NOT NULL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    source_type VARCHAR(40) NOT NULL DEFAULT 'channel',
    url VARCHAR(1024) NOT NULL UNIQUE,
    label VARCHAR(255),
    active BOOLEAN NOT NULL DEFAULT 1,
    last_checked_at DATETIME,
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE clip_intelligence (
    id INTEGER NOT NULL PRIMARY KEY,
    clip_id INTEGER NOT NULL UNIQUE REFERENCES clips(id),
    channel_profile_id INTEGER REFERENCES channel_profiles(id),
    retention_score FLOAT NOT NULL DEFAULT 0,
    viral_probability FLOAT NOT NULL DEFAULT 0,
    curiosity_score FLOAT NOT NULL DEFAULT 0,
    emotional_score FLOAT NOT NULL DEFAULT 0,
    pacing_score FLOAT NOT NULL DEFAULT 0,
    hook_strength_score FLOAT NOT NULL DEFAULT 0,
    conflict_score FLOAT NOT NULL DEFAULT 0,
    danger_score FLOAT NOT NULL DEFAULT 0,
    surprise_score FLOAT NOT NULL DEFAULT 0,
    humor_score FLOAT NOT NULL DEFAULT 0,
    quality_score FLOAT NOT NULL DEFAULT 0,
    hook_type VARCHAR(80),
    decision VARCHAR(40) NOT NULL DEFAULT 'review',
    reasons_json JSON,
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE trend_signals (
    id INTEGER NOT NULL PRIMARY KEY,
    niche_type VARCHAR(80) NOT NULL DEFAULT 'general',
    keyword VARCHAR(140) NOT NULL,
    source VARCHAR(60) NOT NULL DEFAULT 'local_metadata',
    score FLOAT NOT NULL DEFAULT 0,
    velocity FLOAT NOT NULL DEFAULT 0,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    first_seen_at DATETIME,
    last_seen_at DATETIME,
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_trend_keyword_source UNIQUE (niche_type, keyword, source)
);

CREATE TABLE learning_events (
    id INTEGER NOT NULL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    clip_id INTEGER REFERENCES clips(id),
    event_type VARCHAR(60) NOT NULL DEFAULT 'clip_outcome',
    outcome_score FLOAT NOT NULL DEFAULT 0,
    metrics_json JSON,
    features_json JSON,
    learned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE revenue_snapshots (
    id INTEGER NOT NULL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    clip_id INTEGER REFERENCES clips(id),
    upload_id INTEGER REFERENCES uploads(id),
    views INTEGER NOT NULL DEFAULT 0,
    watch_time_hours FLOAT NOT NULL DEFAULT 0,
    estimated_rpm FLOAT NOT NULL DEFAULT 0.06,
    estimated_revenue FLOAT NOT NULL DEFAULT 0,
    projected_monthly_revenue FLOAT NOT NULL DEFAULT 0,
    period_start DATETIME,
    period_end DATETIME,
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE upload_recommendations (
    id INTEGER NOT NULL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    clip_id INTEGER REFERENCES clips(id),
    recommended_for DATETIME,
    confidence_score FLOAT NOT NULL DEFAULT 0,
    rationale TEXT,
    title VARCHAR(120),
    hashtags JSON,
    thumbnail_prompt TEXT,
    status VARCHAR(40) NOT NULL DEFAULT 'recommended',
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE processing_jobs (
    id INTEGER NOT NULL PRIMARY KEY,
    job_type VARCHAR(80) NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'queued',
    priority INTEGER NOT NULL DEFAULT 100,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    payload_json JSON,
    result_json JSON,
    error TEXT,
    stderr_tail TEXT,
    locked_at DATETIME,
    started_at DATETIME,
    finished_at DATETIME,
    next_run_at DATETIME,
    duration_seconds FLOAT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE job_stages (
    id INTEGER NOT NULL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES processing_jobs(id),
    name VARCHAR(120) NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'queued',
    stage_order INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    started_at DATETIME,
    finished_at DATETIME,
    duration_seconds FLOAT,
    stderr_tail TEXT,
    error TEXT,
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_job_stage_name UNIQUE (job_id, name)
);

CREATE TABLE media_assets (
    id INTEGER NOT NULL PRIMARY KEY,
    asset_type VARCHAR(60) NOT NULL,
    file_path VARCHAR(1024) NOT NULL UNIQUE,
    owner_table VARCHAR(80),
    owner_id INTEGER,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    retention_state VARCHAR(40) NOT NULL DEFAULT 'active',
    keep_until DATETIME,
    archived_path VARCHAR(1024),
    last_seen_at DATETIME,
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE calibration_reports (
    id INTEGER NOT NULL PRIMARY KEY,
    sample_count INTEGER NOT NULL DEFAULT 0,
    retention_mae FLOAT,
    virality_mae FLOAT,
    hook_mae FLOAT,
    confidence_low FLOAT,
    confidence_high FLOAT,
    report_json JSON,
    generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_channel_profiles_niche ON channel_profiles(niche_type, active);
CREATE INDEX ix_source_feeds_type_active ON source_feeds(source_type, active);
CREATE INDEX ix_clip_intelligence_scores ON clip_intelligence(retention_score, viral_probability);
CREATE INDEX ix_trend_signals_niche_score ON trend_signals(niche_type, score);
CREATE INDEX ix_learning_events_type_score ON learning_events(event_type, outcome_score);
CREATE INDEX ix_revenue_snapshots_channel_period ON revenue_snapshots(channel_id, period_end);
CREATE INDEX ix_upload_recommendations_status_time ON upload_recommendations(status, recommended_for);
CREATE INDEX ix_review_decisions_clip_action ON review_decisions(clip_id, action);
CREATE INDEX ix_rights_reviews_clip_approved ON rights_reviews(clip_id, approved_for_upload);
CREATE INDEX ix_quality_gate_clip_passed ON quality_gate_results(clip_id, passed);
CREATE INDEX ix_negative_samples_category ON negative_samples(category, severity);
CREATE INDEX ix_processing_jobs_status_next ON processing_jobs(status, next_run_at, priority);
CREATE INDEX ix_job_stages_job_status ON job_stages(job_id, status);
CREATE INDEX ix_media_assets_type_state ON media_assets(asset_type, retention_state);
CREATE INDEX ix_calibration_reports_generated ON calibration_reports(generated_at);
