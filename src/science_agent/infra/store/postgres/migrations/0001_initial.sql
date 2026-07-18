CREATE TABLE IF NOT EXISTS science_agent_state (
    agent_id TEXT PRIMARY KEY,
    info JSONB,
    messages JSONB NOT NULL DEFAULT '[]'::JSONB,
    tool_calls JSONB NOT NULL DEFAULT '[]'::JSONB,
    todos JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT science_agent_state_messages_array
        CHECK (jsonb_typeof(messages) = 'array'),
    CONSTRAINT science_agent_state_tool_calls_array
        CHECK (jsonb_typeof(tool_calls) = 'array'),
    CONSTRAINT science_agent_state_todos_array
        CHECK (jsonb_typeof(todos) = 'array')
);

-- science-agent:split
CREATE TABLE IF NOT EXISTS science_agent_events (
    agent_id TEXT NOT NULL REFERENCES science_agent_state(agent_id) ON DELETE CASCADE,
    seq BIGINT NOT NULL CHECK (seq > 0),
    event_timestamp DOUBLE PRECISION NOT NULL,
    channel TEXT NOT NULL CHECK (channel IN ('progress', 'control', 'monitor')),
    event JSONB NOT NULL CHECK (jsonb_typeof(event) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agent_id, seq)
);

-- science-agent:split
CREATE INDEX IF NOT EXISTS science_agent_events_channel_idx
    ON science_agent_events (agent_id, channel, seq);

-- science-agent:split
CREATE TABLE IF NOT EXISTS science_agent_snapshots (
    agent_id TEXT NOT NULL REFERENCES science_agent_state(agent_id) ON DELETE CASCADE,
    snapshot_id TEXT NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (agent_id, snapshot_id)
);

-- science-agent:split
CREATE INDEX IF NOT EXISTS science_agent_snapshots_updated_idx
    ON science_agent_snapshots (agent_id, updated_at DESC);

