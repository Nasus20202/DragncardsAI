## Context

The `game_action_helpers.py` file contains 20 explicit HTTP endpoints that wrap the generic `/games/{session_id}/actions` endpoint. Each endpoint creates a separate MCP tool when FastMCP derives tools from the FastAPI OpenAPI schema. Currently, most endpoints lack the `summary` parameter that FastAPI uses for OpenAPI documentation and which MCP clients display to users.

## Goals / Non-Goals

**Goals:**
- Add concise summaries to all action helper endpoints
- Help LLM agents understand when to use each tool vs alternatives
- Include warnings for low-level tools that shouldn't be first choice

**Non-Goals:**
- No changes to action behavior
- No new endpoints or capabilities

## Decisions

**Decision 1: Add `summary` directly to existing `@router.post` decorators**
- Rationale: FastAPI/OpenAPI supports this natively; sums appear in `/docs` and MCP tools automatically
- Alternative: Could add description to Pydantic models instead - rejected because endpoint-level summary is more specific to the tool's purpose

**Decision 2: Include "when to use" guidance in summaries**
- Rationale: MCP tool descriptions should help agents choose correctly
- Alternative: Just describe what the tool does - rejected because context-agnostic descriptions don't prevent wrong tool choices

**Decision 3: Add warning to `set_card_property` about using typed alternatives**
- Rationale: Prevents agents from using low-level action when typed actions exist
- Alternative: Remove the endpoint - rejected because it's still useful for edge cases