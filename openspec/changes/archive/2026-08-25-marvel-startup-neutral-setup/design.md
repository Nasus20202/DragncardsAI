# Design: neutral Marvel startup and setup

## Context

DragnCardsAI has two game drivers behind one game-service API. DragnCards is a playtable with
typed composed actions; marvel-lcg is a rules-enforcing engine with enumerated legal options. The
existing marvel-lcg integration is present in the source tree, but its Compose service and
initialization service are profile-gated. Its driver also receives a generic mapping for table
creation and uses the first listed scenario or deck when a value is absent. The generated MCP
surface does not give a generic caller a single setup-discovery contract, and the Marvel harness
reference calls the option routes with `player` even though the API takes `player_n`.

The engine has no stable room identifier and supports one active game per running instance. A
local game-service slug cannot be treated as an engine attachment address or as evidence that a
second table can coexist.

## Goals

- Make a normal local stack start both supported backend engines so platform selection is an API
  decision rather than a Compose-profile decision.
- Let a caller discover setup data and select a scenario and ordered hero decks without knowing
  backend-specific file paths or internal defaults.
- Preserve existing calls that omit optional setup where a safe configured default exists.
- Make the HTTP and generated MCP contracts carry enough capability metadata for a backend-neutral
  client to choose the right move surface.
- Prevent two sessions from concurrently claiming the singleton marvel-lcg engine.

## Non-goals

- Feature parity between the move surfaces.
- A generic engine registry or a third platform.
- Persisting a Marvel game inside game-service or inventing an attachable room id for it.

## Decisions

### Decision 1: Remove profile gating from ordinary startup

The repository-owned Compose definition will include `marvel-lcg` and `marvel-lcg-init` without a
profile. The normal app and infrastructure startup path will start the engine, wait for its
initialization dependency, and expose the configured health/base URL. The engine remains an
internal backend dependency; it is not added to the dashboard's first-party service proxy list.

**Alternative rejected: keep the profile and document a second startup command.** That preserves
the exact failure reported by the user: the ordinary app is unable to create a Marvel game unless a
developer knows and remembers an infrastructure switch. It also makes integration and MCP
discovery depend on an out-of-band deployment choice.

### Decision 2: Use one neutral setup catalog endpoint

Game-service will expose a read-only `list_game_setup_catalog` endpoint and generated MCP tool.
The optional `platform` selector defaults to `dragncards`, and the response is a discriminated
typed catalog carrying `platform` and `move_surface`. Each platform supplies only the setup data
it owns. Marvel entries expose opaque catalog `id` values for scenarios and hero decks; callers
must pass those ids back rather than constructing paths or relying on display names.

The endpoint is the stable discovery path for generic callers. Existing Marvel-specific catalog
routes remain compatible and can delegate to the same driver catalog, but orchestration does not
need to know those route names.

**Alternative rejected: expose only `/marvel-lcg/scenarios` and `/marvel-lcg/decks`.** That forces
every caller to branch on a backend before it can even discover setup and makes the MCP contract
platform-shaped. **Alternative rejected: expose raw engine paths.** Engine paths are transport
details and are not a stable setup identity.

### Decision 3: Pass a typed platform create specification through the seam

`create_game` accepts an optional discriminated `setup`/platform create specification. The
marvel-lcg variant contains `scenario_id` and an ordered, non-empty list of unique
`{seat, hero_deck_id}` entries. The order is preserved when the engine receives hero documents and
is returned as the resolved setup metadata. The DragnCards variant contains its typed plugin
selection, while legacy top-level DragnCards fields are adapted at the API boundary.

The driver protocol accepts this typed specification, not `dict[str, Any]` or `plugin_info`. The
API validates that the setup discriminator agrees with the request platform, every id came from
the selected platform's catalog, seats are neutral `player1` through `player4`, and no seat is
duplicated. The driver then resolves catalog ids to document content at its transport boundary.

**Alternative rejected: keep `plugin_info` and document its keys.** A free-form mapping allows
Marvel fields to be silently ignored or replaced by defaults and couples a non-DragnCards driver
to a DragnCards concept. **Alternative rejected: accept hero names and paths.** Names are not
unique setup identities and paths expose engine layout; catalog ids are the only accepted selection
values.

### Decision 4: Compatibility means optional, not implicit first-catalog selection

Omitting `setup` remains valid for legacy callers. DragnCards follows its existing default and
plugin behavior. Marvel-lcg may use explicitly configured legacy default ids, but those ids are
validated against the live catalog and the selected scenario/decks are returned in session
metadata. If no valid configured defaults exist, creation returns a client error naming
`list_game_setup_catalog`, `scenario_id`, and the ordered player deck entries. The driver never
selects `catalog[0]` as an invisible fallback.

**Alternative rejected: preserve first-catalog fallback.** It makes a successful response lie
about what a caller asked for and is the direct cause of the repeated-heroes defect. **Alternative
rejected: make setup mandatory immediately for every platform.** That breaks existing DragnCards
clients and is unnecessary when a safe, validated legacy default is available.

### Decision 5: Advertise platform and move surface explicitly

The platform driver declares `platform` (`dragncards` or `marvel-lcg`) and `move_surface`
(`typed_actions` or `enumerated_options`). Session metadata, create responses, list responses,
state responses, and the session action catalog carry these fields. A caller uses the metadata to
select tools; the service still enforces the choice server-side. DragnCards keeps typed action
helpers and raw DragnLang, while marvel-lcg exposes only enumerated options. No compatibility
adapter fabricates the other surface.

**Alternative rejected: infer the move surface from the presence of tools.** Tool lists can be
filtered by session and stale clients can cache them, so inference would produce ambiguous or
misdirected calls. **Alternative rejected: put platform details only in `plugin_info`.** Marvel has
no plugin identity, and opaque metadata is not a reliable capability contract.

### Decision 6: Protect the singleton engine with a distributed active lease

Before creating or attaching a Marvel session, game-service acquires a Valkey lease keyed by the
configured Marvel engine endpoint. The lease records the owning session and fencing token, has a
bounded TTL, renews while the live session is healthy, and is released during teardown. A second
claim receives a conflict naming the current singleton constraint. If renewal is lost, the session
is degraded and no move is sent with an unowned lease.

Marvel attachment is rejected as unsupported because the engine exposes no stable external table
id that can safely map to a game-service slug. The local slug remains metadata only and cannot be
used to attach after restart. This is explicit rather than a best-effort connection to whichever
game happens to be active.

**Alternative rejected: keep an in-process boolean.** It does not coordinate multiple service
workers or replicas and loses ownership on process restart. **Alternative rejected: attach by the
local slug.** The slug is generated by our service and is unknown to the engine, so it cannot prove
which table is being attached. **Alternative rejected: allow multiple Marvel sessions.** The
engine's singleton state would make those sessions mutate and observe the same game.

### Decision 7: Keep MCP generated and fix the contract at the route boundary

The neutral setup route receives an explicit readable operation id and is included in the ordinary
game-service MCP surface. Its strict schema is generated from FastAPI exactly like existing routes;
no second hand-written MCP implementation is added. The Marvel option routes continue to be
capability-specific, but both their list query and choice body use `player_n`. The Marvel skill
reference will call `list_game_options(session_id, player_n)` and
`choose_game_option(session_id, player_n, option_id, targets, resources)`.

**Alternative rejected: add an MCP-only setup tool.** That creates a second behavior path that can
drift from HTTP and violates the service's generated-tool construction. **Alternative rejected:
rename the API parameter to match the stale skill prose without a compatibility plan.** The route
schema is the source of truth; the skill must be corrected and tests must pin the generated schema.

## Risks and mitigations

- Starting both engines increases local resource use. The stack already supports both drivers and
  the requirement is ordinary availability; the Marvel engine remains internal and its host port
  stays configurable.
- A stale or invalid legacy default can prevent Marvel creation. Fail before sending an engine
  request and explain the neutral discovery call and required ids instead of creating the wrong
  game.
- A lease can expire during a network partition. Fence all mutating calls with the current token,
  mark the session degraded on renewal failure, and require a new deliberate create after cleanup.
- Catalog contents can change between discovery and creation. Revalidate all ids immediately
  before document fetch and return the invalid id; never substitute another entry.
- Removing the profile changes existing CI assumptions. Update compose readiness checks and tests
  so the ordinary stack asserts the engine and initializer are present.
