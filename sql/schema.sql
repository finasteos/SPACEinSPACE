-- ============================================================================
-- Supabase schema for the agent-ecosystem
-- ============================================================================
-- Idempotent: every statement uses CREATE … IF NOT EXISTS or OR REPLACE so it
-- can be safely re-applied.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ─── Agent memories (pgvector) ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    memory_type TEXT CHECK (memory_type IN ('episodic', 'semantic', 'procedural', 'scratchpad')),
    content TEXT NOT NULL,
    embedding VECTOR(4096),
    metadata JSONB DEFAULT '{}'::jsonb,
    parent_id UUID REFERENCES agent_memories(id) ON DELETE SET NULL,
    confidence FLOAT DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    source TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ   -- NULL = permanent; non-null = TTL
);

-- Note: ivfflat indexes support up to 2000 dimensions in pgvector.
-- For VECTOR(4096), exact distance queries (<=>) in match_memories work without ivfflat index.
-- CREATE INDEX IF NOT EXISTS idx_memories_embedding
--     ON agent_memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_memories_agent ON agent_memories (agent_id, memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_content_trgm
    ON agent_memories USING gin (content gin_trgm_ops);

-- ─── Agent conversations (A2A log) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id TEXT NOT NULL,
    message_id TEXT NOT NULL UNIQUE,
    from_agent TEXT NOT NULL,
    to_agent TEXT,
    message_type TEXT NOT NULL CHECK (message_type IN (
        'task', 'question', 'answer', 'tool_call', 'tool_result',
        'observation', 'error', 'plan_update', 'heartbeat', 'human_input'
    )),
    content TEXT NOT NULL,
    embedding VECTOR(4096),
    tool_calls JSONB DEFAULT '[]'::jsonb,
    latency_ms INT,
    metadata JSONB DEFAULT '{}'::jsonb,
    parent_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- CREATE INDEX IF NOT EXISTS idx_conversations_embedding
--     ON agent_conversations USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_conversations_thread
    ON agent_conversations (thread_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_content_trgm
    ON agent_conversations USING gin (content gin_trgm_ops);

-- ─── Scratchpad ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scratchpad (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id TEXT NOT NULL,
    agent_id TEXT,
    section TEXT NOT NULL DEFAULT 'general',
    content TEXT NOT NULL,
    version INT NOT NULL DEFAULT 1,
    metadata JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraint so we always have a logical "latest per section"
    UNIQUE (thread_id, section, version)
);

CREATE INDEX IF NOT EXISTS idx_scratchpad_thread_version
    ON scratchpad (thread_id, section, version DESC);
CREATE INDEX IF NOT EXISTS idx_scratchpad_section
    ON scratchpad (section);

-- ─── Agent registry ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN (
        'planner', 'blender', 'unity', 'godot', 'memory', 'tool',
        'review', 'fallback', 'human', 'inhabitant', 'world'
    )),
    status TEXT NOT NULL DEFAULT 'idle' CHECK (status IN (
        'idle', 'active', 'thinking', 'waiting', 'error', 'paused'
    )),
    capabilities TEXT[] DEFAULT '{}'::text[],
    current_thread_id TEXT,
    last_heartbeat TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Keep role allowlist in sync on re-apply (CREATE TABLE IF NOT EXISTS is a no-op
-- once the table exists). Safe to run every apply_schema.py invocation.
ALTER TABLE agents DROP CONSTRAINT IF EXISTS agents_role_check;
ALTER TABLE agents ADD CONSTRAINT agents_role_check CHECK (role IN (
    'planner', 'blender', 'unity', 'godot', 'memory', 'tool',
    'review', 'fallback', 'human', 'inhabitant', 'world'
));

CREATE INDEX IF NOT EXISTS idx_agents_status ON agents (status);
CREATE INDEX IF NOT EXISTS idx_agents_heartbeat ON agents (last_heartbeat DESC);

-- ─── Tool call log ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tool_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_version TEXT,
    input_params JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_result JSONB,
    success BOOLEAN,
    error_message TEXT,
    latency_ms INT,
    scratchpad_version INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_thread ON tool_calls (thread_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tool_calls_agent  ON tool_calls (agent_id, tool_name);

-- ─── Triggers: bump updated_at on row modification ─────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE 'plpgsql';

DROP TRIGGER IF EXISTS tg_memories_updated ON agent_memories;
CREATE TRIGGER tg_memories_updated BEFORE UPDATE ON agent_memories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS tg_scratchpad_updated ON scratchpad;
CREATE TRIGGER tg_scratchpad_updated BEFORE UPDATE ON scratchpad
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ─── RPC: match_memories ───────────────────────────────────────────────────
-- pgvector cosine-distance vector search with metadata filters and TTL
CREATE OR REPLACE FUNCTION match_memories(
    query_embedding VECTOR(4096),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 10,
    agent_filter TEXT DEFAULT NULL,
    type_filter TEXT DEFAULT NULL,
    thread_filter TEXT DEFAULT NULL
)
RETURNS TABLE(
    id UUID,
    agent_id TEXT,
    memory_type TEXT,
    content TEXT,
    confidence FLOAT,
    similarity FLOAT,
    created_at TIMESTAMPTZ,
    metadata JSONB
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        am.id,
        am.agent_id,
        am.memory_type,
        am.content,
        am.confidence,
        1 - (am.embedding <=> query_embedding) AS similarity,
        am.created_at,
        am.metadata
    FROM agent_memories am
    WHERE (am.embedding <=> query_embedding) < (1 - match_threshold)
      AND (agent_filter   IS NULL OR am.agent_id     = agent_filter)
      AND (type_filter    IS NULL OR am.memory_type  = type_filter)
      AND (thread_filter  IS NULL OR am.metadata->>'thread_id' = thread_filter)
      AND (am.expires_at IS NULL OR am.expires_at > NOW())
    ORDER BY am.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- ─── RPC: latest scratchpad rows per section ───────────────────────────────
CREATE OR REPLACE FUNCTION get_scratchpad(p_thread_id TEXT)
RETURNS TABLE(
    section TEXT,
    content TEXT,
    version INT,
    agent_id TEXT,
    updated_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT ON (s.section)
        s.section,
        s.content,
        s.version,
        s.agent_id,
        s.updated_at
    FROM scratchpad s
    WHERE s.thread_id = p_thread_id
    ORDER BY s.section ASC, s.version DESC;
END;
$$;

-- ─── Row-Level Security ────────────────────────────────────────────────────
ALTER TABLE agents        ENABLE ROW LEVEL SECURITY;
ALTER TABLE tool_calls    ENABLE ROW LEVEL SECURITY;
ALTER TABLE scratchpad    ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_memories     ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_conversations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS service_all_agents        ON agents;
DROP POLICY IF EXISTS service_all_tool_calls    ON tool_calls;
DROP POLICY IF EXISTS service_all_scratchpad    ON scratchpad;
DROP POLICY IF EXISTS service_all_memories      ON agent_memories;
DROP POLICY IF EXISTS service_all_conversations ON agent_conversations;

CREATE POLICY service_all_agents        ON agents        FOR ALL TO service_role USING (true);
CREATE POLICY service_all_tool_calls    ON tool_calls    FOR ALL TO service_role USING (true);
CREATE POLICY service_all_scratchpad    ON scratchpad    FOR ALL TO service_role USING (true);
CREATE POLICY service_all_memories      ON agent_memories     FOR ALL TO service_role USING (true);
CREATE POLICY service_all_conversations ON agent_conversations FOR ALL TO service_role USING (true);

-- Read access for the chat-UI (anon role)
DROP POLICY IF EXISTS anon_read_agents ON agents;
CREATE POLICY anon_read_agents ON agents FOR SELECT TO anon USING (true);
