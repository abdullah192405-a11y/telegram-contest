-- Run this in Supabase Dashboard → SQL Editor (or via supabase db query)

CREATE TABLE IF NOT EXISTS participants (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    telegram_username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    invite_link TEXT UNIQUE,
    link_name TEXT UNIQUE,
    joins_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS joins_log (
    id BIGSERIAL PRIMARY KEY,
    participant_id BIGINT REFERENCES participants(id) ON DELETE CASCADE,
    joined_user_name TEXT,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Block public API access; the Flask server connects with the postgres role directly.
ALTER TABLE participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE joins_log ENABLE ROW LEVEL SECURITY;
