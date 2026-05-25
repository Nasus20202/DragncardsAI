## Context

The game-service already exposes MCP tools for live card search, but prebuilt set metadata still lives only in the plugin data files. LLM clients cannot currently discover the available Marvel Champions sets before choosing a load target or recommending a scenario/deck.

This change is constrained to the game-service and Marvel Champions plugin data. It should stay read-only and should not alter DragnCards state, room behavior, or deck loading semantics.

## Goals / Non-Goals

**Goals:**
- Expose prebuilt Marvel Champions set metadata through MCP.
- Allow clients to list and filter the available sets.
- Return a normalized summary with the set id, name, and type.
- Keep the implementation consistent with the existing provider-based catalog pattern.

**Non-Goals:**
- No changes to how decks are loaded into a session.
- No write/update operations for the set catalog.
- No UI/dashboard work.
- No changes to DragnCards or the upstream plugin format.

## Decisions

1. Add a dedicated set-catalog service path in `game-service` rather than overloading card search.
   - Rationale: sets are a different concept from cards and should have a distinct return shape and tool name.
   - Alternatives considered: extend `search_cards_marvel_champions` with set-related filters. Rejected because it mixes card and set semantics and makes the response shape ambiguous.

2. Source set metadata from the Marvel Champions plugin's `sets.json` through the existing provider layer.
   - Rationale: provider-owned data keeps the catalog aligned with the plugin artifacts already mounted into the backend.
   - Alternatives considered: hard-code the set list in game-service or read the file directly from the MCP router. Rejected because both duplicate provider knowledge and make future plugin changes harder to isolate.

3. Expose a single read-only MCP tool that supports optional filters.
   - Rationale: the user need is discovery and filtering, not a separate browse/search split.
   - Alternatives considered: separate list and search tools. Rejected because the data set is small and a single tool keeps the MCP surface smaller.

4. Keep filtering simple and predictable.
   - Rationale: name filters should be substring matches and type filters should be exact matches so LLMs can use them without needing provider-specific heuristics.
   - Alternatives considered: fuzzy matching or ranked search. Rejected because it adds complexity without improving the basic discovery workflow.

## Risks / Trade-offs

- [Upstream plugin schema changes] -> The `sets.json` shape may change upstream and break parsing. Mitigation: normalize through the provider layer and cover the parser with unit tests against fixture data.
- [Incomplete metadata] -> Some set entries may omit optional fields or use inconsistent type labels. Mitigation: define a minimal required output (`id`, `name`, `type`) and pass through only the fields the tool needs.
- [MCP surface growth] -> Adding more discovery tools can make tool lists noisy. Mitigation: keep this feature focused on one small catalog tool and reuse the existing provider naming conventions.

## Migration Plan

1. Add the set catalog data access in the game-service provider layer.
2. Register the MCP tool and update tool discovery.
3. Add unit coverage for filtering and MCP exposure.
4. Verify the tool returns only read-only metadata and does not affect sessions.

Rollback is straightforward: remove the tool registration and catalog service code. No schema migration or persistent data backfill is required.

## Open Questions

- Should the tool expose one provider-specific catalog per plugin, or only the Marvel Champions catalog for now?
- Should type filtering use the raw plugin type string or a normalized display label?
