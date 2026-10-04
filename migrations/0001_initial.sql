CREATE TABLE profiles (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(btrim(name)) > 0),
    mode TEXT NOT NULL DEFAULT 'OFF' CHECK (mode IN ('OFF', 'ON', 'SCHEDULE')),
    cooldown_seconds INTEGER NOT NULL CHECK (cooldown_seconds >= 0),
    delay_min_seconds INTEGER NOT NULL DEFAULT 0 CHECK (delay_min_seconds >= 0),
    delay_max_seconds INTEGER NOT NULL DEFAULT 0 CHECK (delay_max_seconds >= delay_min_seconds),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE rule_groups (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0)
);

CREATE TABLE rule_terms (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id BIGINT NOT NULL REFERENCES rule_groups(id) ON DELETE CASCADE,
    term TEXT NOT NULL,
    normalized_term TEXT NOT NULL CHECK (length(normalized_term) > 0)
);

CREATE TABLE not_terms (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    term TEXT NOT NULL,
    normalized_term TEXT NOT NULL CHECK (length(normalized_term) > 0)
);

CREATE TABLE reply_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    text TEXT NOT NULL CHECK (length(text) > 0)
);

CREATE TABLE schedule_windows (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_minute SMALLINT NOT NULL CHECK (start_minute BETWEEN 0 AND 1439),
    end_minute SMALLINT NOT NULL CHECK (end_minute BETWEEN 1 AND 1440),
    CHECK (start_minute < end_minute)
);

CREATE TABLE telegram_updates (
    chat_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ignored', 'queued', 'failed')),
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chat_id, message_id)
);

CREATE TABLE contact_history (
    profile_id BIGINT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    sender_id BIGINT NOT NULL,
    last_sent_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (profile_id, sender_id)
);

CREATE TABLE recipient_opt_outs (
    sender_id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE outbound_jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_id BIGINT REFERENCES profiles(id) ON DELETE SET NULL,
    source_chat_id BIGINT NOT NULL,
    source_message_id BIGINT NOT NULL,
    sender_id BIGINT NOT NULL,
    reply_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sending', 'sent', 'cancelled', 'failed', 'ambiguous')),
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    claimed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_class TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_chat_id, source_message_id)
);

CREATE TABLE event_logs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type TEXT NOT NULL,
    profile_id BIGINT REFERENCES profiles(id) ON DELETE SET NULL,
    source_chat_id BIGINT,
    source_message_id BIGINT,
    sender_id BIGINT,
    detail TEXT
);

CREATE INDEX idx_groups_profile ON rule_groups(profile_id, position, id);
CREATE INDEX idx_windows_profile ON schedule_windows(profile_id, weekday, start_minute);
CREATE INDEX idx_logs_created ON event_logs(created_at DESC);
CREATE INDEX idx_outbound_ready ON outbound_jobs(status, available_at, id);
CREATE INDEX idx_updates_processed ON telegram_updates(processed_at);
