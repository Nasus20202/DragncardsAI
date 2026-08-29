## Context

See `proposal.md` for the user-visible failure. The Marvel driver currently hashes each raw path returned by `/list_scenarios` and `/list_starter_deck` independently in setup discovery and creation. The vendored engine's configured folders currently produce paths beginning with `./`, but equivalent deployments or requests can return the same relative document without that prefix. Because the raw spelling is part of the hash input, a freshly returned opaque id can fail creation even though the underlying document is present.

The driver must continue fetching documents through the engine's allowlisted document endpoints and must not turn caller-supplied paths into accepted setup identities.

## Goals / Non-Goals

**Goals:**

- Keep the existing opaque ids and the reported `hero-deck:377e837cafe661012d4e09eb` value valid when it was produced from `./deck/starter/spider_man.json`.
- Resolve catalog membership across the only representation difference known to be harmless: one leading `./`.
- Use the path from the live creation listing for document retrieval.
- Preserve rejection of unknown opaque ids and raw paths.

**Non-Goals:**

- No engine, Docker, or deployment configuration changes.
- No broad path canonicalization that could change directory semantics or permit traversal.
- No lease, session, or creation-order changes.

## Decisions

### Store aliases for equivalent listing spellings

Build catalog maps with the existing `_catalog_id` function for each live path and, when applicable, its leading-`./` counterpart. Map every alias to the path returned by the current creation listing. This keeps the id already emitted by setup discovery stable while accepting the equivalent id generated during creation.

**Alternative rejected:** change `_catalog_id` to hash only a normalized path. That would make future catalog responses consistent but would change the ids already returned to clients and invalidate persisted or copied setup selections. Alias lookup is backward-compatible and limited in scope.

### Normalize only the leading relative marker

Use a small internal path-variant helper that returns the raw path and exactly one equivalent spelling with a leading `./` added or removed. Do not use unrestricted filesystem normalization or resolve paths on the game-service host; the paths are engine-owned document identifiers, not local files.

**Alternative rejected:** use `os.path.normpath` or `Path.resolve`. Those APIs can erase meaningful engine path syntax, consult the wrong filesystem, and create a path traversal policy that does not match the engine's document endpoint.

### Keep raw live paths as map values

The alias map keys are opaque ids; values remain the exact engine paths from the creation-time listing. `create_table` therefore calls `get_scenario_json` and `get_hero_json` with engine-returned paths, while explicit raw path inputs never become map keys and remain rejected.

**Alternative rejected:** reconstruct a path from the submitted id. Opaque ids are intentionally non-reversible and reconstruction would risk accepting fabricated identifiers.

## Risks / Trade-offs

- The engine controls listing responses and could introduce other spelling differences not covered by this change; those remain unavailable rather than being guessed. The regression test pins the supported `./` variation.
- If two distinct engine paths collapse under the supported leading-marker variant, the later map assignment would select one path. The engine's relative-path contract treats those spellings as equivalent; no filesystem-wide normalization is performed.
- A live singleton Marvel game prevents end-to-end creation of a second game. Verification therefore includes deterministic driver tests and the existing integration coverage; the active game must not be deleted as part of this fix.
