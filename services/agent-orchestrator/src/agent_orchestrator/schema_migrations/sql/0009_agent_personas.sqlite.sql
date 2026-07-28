-- Reusable, user-authored agent personas: a system prompt, a skill selection,
-- and a tool configuration a subagent can be started from.
--
-- NULL provider_id / model_name inherit the spawning session's values.
-- NULL skills_json inherits the session's enabled skills, and a list of names
-- replaces them.
-- NULL allowed_tools_json means no narrowing, and a list is an allowlist that
-- can only REMOVE tools from what the child session already exposes.
--
-- Deployment-global and keyed by name, like skill_registries and mcp_registries.
--
-- Note for editors: the shared migration runner splits this file on semicolons,
-- so a comment must not contain one.
CREATE TABLE agent_personas (
    name TEXT PRIMARY KEY,
    display_name TEXT,
    description TEXT,
    system_prompt TEXT NOT NULL,
    provider_id TEXT,
    model_name TEXT,
    gateway_options JSON NOT NULL,
    provider_options JSON NOT NULL,
    skills_json JSON,
    allowed_tools_json JSON,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- The persona a spawn from this session falls back to when the agent names none.
-- Deliberately not a foreign key. SQLite does not enforce foreign keys unless a
-- per-connection pragma is set, so the "deleting a persona clears it as a
-- default" rule is applied explicitly in the repository instead, which keeps
-- PostgreSQL and SQLite behaviour identical.
ALTER TABLE agent_sessions ADD COLUMN default_subagent_persona TEXT;
