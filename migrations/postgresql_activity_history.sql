CREATE TABLE IF NOT EXISTS activity_history (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    session_id BIGINT,
    event_time TIMESTAMPTZ NOT NULL,

    login_time TIMESTAMPTZ,
    logout_time TIMESTAMPTZ,
    session_status TEXT DEFAULT '',
    login_status TEXT DEFAULT '',
    logout_status TEXT DEFAULT '',

    original_query TEXT,
    canonical_query TEXT DEFAULT '',
    transliterated_query TEXT DEFAULT '',
    detected_language TEXT DEFAULT '',
    preferred_language TEXT DEFAULT '',
    input_mode TEXT DEFAULT 'text',
    provider TEXT DEFAULT '',
    document_type TEXT DEFAULT '',
    searched_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER DEFAULT 0,
    results_count INTEGER DEFAULT 0,

    document_id BIGINT,
    document_name TEXT DEFAULT '',
    document_path TEXT DEFAULT '',
    source TEXT DEFAULT 'local',
    action TEXT DEFAULT 'open',
    search_history_id BIGINT,

    status TEXT NOT NULL DEFAULT 'PASS',
    error_message TEXT DEFAULT '',
    event_reason TEXT DEFAULT '',
    details_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_activity_user_time
    ON activity_history(username, event_time DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_activity_session_time
    ON activity_history(session_id, event_time DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_activity_event_time
    ON activity_history(event_type, event_time DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_activity_user_event
    ON activity_history(username, event_type, event_time DESC, id DESC);
