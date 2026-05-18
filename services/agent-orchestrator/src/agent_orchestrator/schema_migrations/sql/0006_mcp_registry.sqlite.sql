-- Create global MCP registry table
CREATE TABLE mcp_registries (
    name VARCHAR(255) PRIMARY KEY,
    transport VARCHAR(64) NOT NULL,
    server_url TEXT NOT NULL,
    headers_json JSON NOT NULL,
    custom BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL
);

-- Create session MCP enablement table
CREATE TABLE session_enabled_mcps (
    session_id VARCHAR(36) NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    mcp_name VARCHAR(255) NOT NULL REFERENCES mcp_registries(name),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_session_mcp_enabled UNIQUE (session_id, mcp_name)
);

-- Drop old per-session MCP assignments table
DROP TABLE IF EXISTS session_mcp_assignments;