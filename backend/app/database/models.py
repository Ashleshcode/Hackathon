"""SQLite schema for campaigns and the coordination graph.

Timestamps are stored as UTC text ending in Z. `media_hash` is only the hash
supplied by an imported post. `sha256` is a cryptographic hash of stored file
bytes and is not a perceptual fingerprint.
"""

TABLES_SQL = """
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    provenance TEXT NOT NULL,
    source_file TEXT,
    parent_campaign_id TEXT REFERENCES campaigns(campaign_id),
    extension_post_json TEXT,
    import_summary_json TEXT NOT NULL,
    algorithm_json TEXT,
    limitations_json TEXT,
    clusters_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
    node_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    label TEXT NOT NULL,
    node_type TEXT NOT NULL,
    cluster_id TEXT,
    post_count INTEGER NOT NULL,
    is_checked_post INTEGER,
    position INTEGER NOT NULL,
    UNIQUE (campaign_id, node_id)
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
    post_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    account_id TEXT NOT NULL,
    timestamp TEXT,
    text TEXT,
    url TEXT,
    media_hash TEXT,
    media_reference TEXT,
    position INTEGER NOT NULL,
    UNIQUE (campaign_id, platform, post_id)
);

CREATE TABLE IF NOT EXISTS media_assets (
    id INTEGER PRIMARY KEY,
    asset_id TEXT UNIQUE,
    campaign_id TEXT REFERENCES campaigns(campaign_id),
    post_row_id INTEGER REFERENCES posts(id),
    media_type TEXT,
    storage_name TEXT,
    byte_size INTEGER,
    sha256 TEXT,
    media_hash TEXT,
    media_reference TEXT,
    created_at TEXT,
    UNIQUE (post_row_id)
);

CREATE TABLE IF NOT EXISTS analysis_jobs (
    id INTEGER PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE,
    campaign_id TEXT REFERENCES campaigns(campaign_id),
    post_id TEXT,
    platform TEXT,
    media_asset_id INTEGER REFERENCES media_assets(id),
    status TEXT NOT NULL,
    status_reason TEXT,
    result_json TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS graph_edges (
    id INTEGER PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
    edge_id TEXT NOT NULL,
    source_node TEXT NOT NULL,
    target_node TEXT NOT NULL,
    signals_json TEXT NOT NULL,
    position INTEGER NOT NULL,
    UNIQUE (campaign_id, edge_id)
);

CREATE TABLE IF NOT EXISTS campaign_sources (
    id INTEGER PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
    platform TEXT NOT NULL,
    query TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (campaign_id, platform)
);

CREATE TABLE IF NOT EXISTS x_accounts (
    id INTEGER PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
    account_id TEXT NOT NULL,
    username TEXT,
    display_name TEXT,
    verified INTEGER,
    verified_type TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE (campaign_id, account_id)
);

CREATE TABLE IF NOT EXISTS x_post_details (
    post_row_id INTEGER PRIMARY KEY REFERENCES posts(id),
    conversation_id TEXT,
    public_metrics_json TEXT,
    origin TEXT NOT NULL,
    source_endpoint TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS x_media (
    id INTEGER PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
    post_row_id INTEGER NOT NULL REFERENCES posts(id),
    media_key TEXT NOT NULL,
    media_type TEXT,
    url TEXT,
    preview_image_url TEXT,
    duration_ms INTEGER,
    width INTEGER,
    height INTEGER,
    alt_text TEXT,
    variants_json TEXT,
    storage_name TEXT,
    ingested_at TEXT NOT NULL,
    UNIQUE (post_row_id, media_key)
);

CREATE TABLE IF NOT EXISTS post_relationships (
    id INTEGER PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
    platform TEXT NOT NULL,
    source_post_id TEXT NOT NULL,
    referencing_post_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    evidence TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    referenced_resolved INTEGER NOT NULL,
    UNIQUE (campaign_id, platform, source_post_id, referencing_post_id, relationship_type)
);

CREATE TABLE IF NOT EXISTS x_sync_runs (
    id INTEGER PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
    status TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS youtube_contexts (
    id INTEGER PRIMARY KEY,
    context_id TEXT NOT NULL UNIQUE,
    video_id TEXT NOT NULL UNIQUE,
    video_url TEXT,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

"""

INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_campaigns_created_at ON campaigns(created_at);
CREATE INDEX IF NOT EXISTS idx_accounts_campaign ON accounts(campaign_id);
CREATE INDEX IF NOT EXISTS idx_posts_campaign ON posts(campaign_id);
CREATE INDEX IF NOT EXISTS idx_posts_media_hash ON posts(media_hash);
CREATE INDEX IF NOT EXISTS idx_media_assets_hash ON media_assets(media_hash);
CREATE INDEX IF NOT EXISTS idx_media_assets_sha256 ON media_assets(sha256);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_campaign ON analysis_jobs(campaign_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_campaign ON graph_edges(campaign_id);
CREATE INDEX IF NOT EXISTS idx_x_accounts_campaign ON x_accounts(campaign_id);
CREATE INDEX IF NOT EXISTS idx_x_media_campaign ON x_media(campaign_id);
CREATE INDEX IF NOT EXISTS idx_post_relationships_campaign ON post_relationships(campaign_id);
CREATE INDEX IF NOT EXISTS idx_x_sync_runs_campaign ON x_sync_runs(campaign_id);
CREATE INDEX IF NOT EXISTS idx_youtube_contexts_video ON youtube_contexts(video_id);
"""
