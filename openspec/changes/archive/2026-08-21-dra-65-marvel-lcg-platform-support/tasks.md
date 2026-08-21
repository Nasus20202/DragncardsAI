# Tasks

## 1. Platform seam in game-service (DragnCards only, no behaviour change)

- [x] 1.1 Add a `platform` slug type with values `dragncards` and `marvel-lcg`, defaulting to `dragncards`, and a platform registry keyed by it
- [x] 1.2 Define the `GamePlatform` driver protocol covering authenticate, create table, attach, connect, request state, execute move, seat control, spectator control, and teardown
- [x] 1.3 Extract `PhoenixRoom` into `DragnCardsPlatform` implementing that protocol, keeping every existing event name and payload byte-identical
- [x] 1.4 Retype `GameSession` to hold a driver instead of `PhoenixClient`/`Channel`/`PhoenixRoom`
- [x] 1.5 Move `set_game` payload construction out of `GameSession` and behind the driver
- [x] 1.6 Move the `"ABORT:"` / `"Error in Marvel Champions triggered"` message grep behind the driver as a bad-game-state signal, raising the same error type from both call sites
- [x] 1.7 Retype `SessionManager` to take a platform rather than `dragncards_http_url`/`dragncards_ws_url`/`email`/`password`, resolving credentials through the driver
- [x] 1.8 Add `platform` to `SessionMetadata`, the session store record, and the create/attach request models, defaulting to `dragncards`
- [x] 1.9 Make `plugin_id`/`plugin_version`/`plugin_name` DragnCards-scoped rather than required session fields
- [x] 1.10 Unit tests: the driver protocol is satisfied by the DragnCards implementation, and a session carries its platform through the store round-trip
- [x] 1.11 Confirm the whole existing game-service unit suite passes **unedited**, and that `test_mcp_server.py`, `test_app_strict_request_bodies.py`, `test_capabilities.py` and `test_cors.py` are untouched

## 2. Per-platform state normalisation and lazy vocabularies

- [x] 2.1 Define the `StateNormaliser` protocol and a per-platform registry, invoked below `GameSession`
- [x] 2.2 Move `_simplify_marvel_state` and `STEP_DESCRIPTIONS` out of `api/routers/game_state.py` into the DragnCards normaliser
- [x] 2.3 Replace all four `plugin_name == "marvel-champions"` branches (`game_state.py` ×2, `game_room.py` ×2) with one polymorphic call
- [x] 2.4 Add `playRound` to the projection, with DragnCards' `roundNumber + 1` conversion living only in its normaliser, and stop exposing the raw counter
- [x] 2.5 Add `phase` (closed set `setup`/`player`/`villain`/`passive`/`unknown`) and opaque `phaseLabel`, mapping DragnCards `1.1`/`1.2`→`player`, `2.1`–`2.5`→`villain`, `0.0`/`0.1`→`passive` so the runtime guard's conclusions are unchanged
- [x] 2.6 Add the optional `pendingSeats` field, omitted entirely for DragnCards
- [x] 2.7 Make `GroupId` and `LayoutId` generation lazy and per-platform so `api/enums.py` performs no work at import time
- [x] 2.8 Remove the unused `marvel_champions.plugin_metadata` import from `logic/actions.py`
- [x] 2.9 Unit test: the app imports, builds, and serves its OpenAPI document with no Marvel Champions plugin JSON or card data on disk
- [x] 2.10 Unit test: the DragnCards simplified-state output is byte-identical to the pre-change projection for a fixed raw-state fixture, apart from the documented new fields
- [x] 2.11 Regenerate and diff the OpenAPI document; any change to an existing DragnCards tool schema is a regression to fix, not to accept

## 3. Vendoring marvel-lcg and infrastructure

- [x] 3.1 Add `external/marvel-lcg` as a submodule of `https://github.com/z00lus/marvel-lcg.git`, pinned to a commit, not tracking a branch
- [x] 3.2 Add `external/docker/marvel-lcg/Dockerfile`, derived from the fork's but building from the submodule with the repo root as build context
- [x] 3.3 Add the compose service: joined to `dragncards-shared`, port `${MARVEL_LCG_PORT:-4006}`→2345, behind a compose profile so a bare `docker compose up` still starts exactly today's DragnCards stack
- [x] 3.4 Supply a `launch.json` override or CLI flags setting a required password and pointing statistics/replay/runtime paths at container volumes
- [x] 3.5 Add `MARVEL_LCG_*` variables to `docker-compose.yaml`, `services/game-service/.env.example`, and the dashboard config
- [x] 3.6 Add the compose file to `INFRA_COMPOSE_FILES` in `scripts/docker-infrastructure.sh`, confirming the derived service list still excludes profile-gated services
- [x] 3.7 Add the image pin to the `Makefile` alongside the three `DRAGNCARDS_*_IMAGE` entries
- [x] 3.8 Update `.github/workflows/test.yaml` readiness gating and `publish.yaml` bake targets
- [x] 3.9 Update `renovate.json` so the new submodule is tracked on the same terms as the existing two
- [x] 3.10 Verify a fresh `git worktree add` plus `git submodule update --init --recursive` yields a working checkout of both submodules
- [x] 3.11 Test: the marvel-lcg container refuses to start without a password configured
- [x] 3.12 Test: `/debug` is unreachable through every first-party surface, asserted against our own routing rather than relying on the platform to refuse it

## 4. marvel-lcg HTTP transport client

- [x] 4.1 Add the HTTP client with an explicitly unsafe cookie jar, so the `app_version` cookie survives an IP-address host
- [x] 4.2 Implement `POST /authenticate` and the `session_token` cookie, plus direct `md5(password)` cookie construction
- [x] 4.3 Implement `GET /get_version` to obtain the `app_version` cookie before any gated call
- [x] 4.4 Assert `Content-Type` on every response and raise a typed error when HTML arrives with HTTP 200, rather than parsing it
- [x] 4.5 Implement `GET /list_scenarios`, `/list_starter_deck`, `/get_scenario_json`, `/get_hero_json`, handling gzip
- [x] 4.6 Implement `GET /new`, building `NewGameDescriptor` with **stringified document content** for `campaign_json` and `hero_json`, and surface its `400`/`409` error bodies as typed errors
- [x] 4.7 Implement `GET /get_world` and `GET /get_ask`, treating `{}` from `/get_ask` as "nothing pending" and parsing the nested `options_json` string
- [x] 4.8 Implement `POST /post` with the exact form-encoded `{id, targets, resources}` body, and `id: 0` for decline
- [x] 4.9 Implement `GET /client_updated` acknowledgement
- [x] 4.10 Unit tests for each call against recorded fixtures, including the HTML-with-200 case and the gzip path

## 5. marvel-lcg render-frame WebSocket

- [x] 5.1 Implement the `WS /ws?p=<seat>` connection and the `Connected <url>` handshake message
- [x] 5.2 Parse `FrameDescriptor` with the fork's exact field set, and parse `notify_texts` entries as JSON strings
- [x] 5.3 Coalesce frames so a per-engine-step burst does not become one event each, and expose the latest frame to the driver
- [x] 5.4 Treat `render_id == -1` as game over
- [x] 5.5 Implement reconnection, and re-send the handshake on reconnect
- [x] 5.6 Implement stuck-prompt detection keyed on the recurring `(render_id, ask_players, prompt_text, option ids)` tuple, explicitly not on `render_id` alone, because the ask frame repeats the previous `render_id`
- [x] 5.7 Implement a bounded submission-attempt cap per prompt so a rejected submission cannot trigger the engine's unbounded retry loop
- [x] 5.8 Unit tests: frame coalescing, game-over detection, a repeated `render_id` treated as normal, and a recurring prompt tuple treated as stuck

## 6. marvel-lcg driver, normaliser, and enumerated-option surface

- [x] 6.1 Implement `MarvelLcgPlatform` against the driver protocol, enforcing the create → connect → play bring-up order
- [x] 6.2 Map neutral seats `player1`..`player4` to `p=0`..`p=3` at the transport edge only
- [x] 6.3 Implement the marvel-lcg state normaliser: `playRound` from `round_id` unchanged, `phase`/`phaseLabel`, `pendingSeats` from `ask_players`
- [x] 6.4 Map its zones by meaning onto the neutral zone names, per seat and shared
- [x] 6.5 Honour per-seat visibility (`visible_for_players`, `is_face_up`, `down_card_ids`), collapsing to the existing `HIDDEN` form
- [x] 6.6 Normalise `players[].resources` from its string form, omitting rather than faking an uninterpretable value
- [x] 6.7 Build the agent-facing option list keyed by option id, enriched with each target card's name and type resolved from the world payload, so two options both named `Play` are distinguishable
- [x] 6.8 Carry the target-count range through, and ignore the legal-target list when the maximum is 0
- [x] 6.9 Normalise prompt text, stripping leading newlines and decorative dashes
- [x] 6.10 Expose a cancel/decline affordance only when the platform offers one
- [x] 6.11 Refuse locally a chosen option id absent from the current option set, or a target selection outside the range, rather than sending it
- [x] 6.12 Add the HTTP routes with explicit `operation_id`s for listing options, choosing an option, and listing scenarios and decks, all with strict request bodies
- [x] 6.13 Confirm the derived MCP tool names and the pinned exclusion set, adding the new tools deliberately
- [x] 6.14 Emit history events on prompts and completed moves only, never per frame
- [x] 6.15 Add OTel spans for game creation, socket lifecycle, world and ask fetch, and move submission, carrying the driver's concluded outcome rather than the platform's meaningless `200`
- [x] 6.16 Assert no span attribute carries world state, prompt text, option or target lists, notify text, or the platform password
- [x] 6.17 Integration test: create a game, connect, receive a prompt, submit an enumerated option chosen by id, and observe the state advance — retry-bounded so it cannot spin the engine

## 7. history-service platform discriminator

- [x] 7.1 Add `platform` to `EventEnvelope`, optional on the wire and defaulting to `dragncards`, refusing an unknown slug
- [x] 7.2 Write migration `0002_platform.postgresql.sql`: add the column to `events` and `snapshots` as `NOT NULL DEFAULT 'dragncards'`, widen all three unique constraints, and join both `game_id` indexes
- [x] 7.3 Write migration `0002_platform.sqlite.sql` using the table-rebuild pattern from eval-service's `0002_target_player.sqlite.sql`
- [x] 7.4 Verify neither migration contains a semicolon inside a string literal or a `DO $$ … $$` block, since the shared runner splits on a naive `;`
- [x] 7.5 Scope the sequence series, the `crc32` advisory lock, and the idempotency key to `(game_id, platform)`
- [x] 7.6 Add `platform` to the commit path's explicit column list, so it is not silently discarded
- [x] 7.7 Carry `platform` on game listings and make listings filterable by it
- [x] 7.8 Add `platform` to the export bundle header, and import a bundle without it as `dragncards`
- [x] 7.9 Refuse a snapshot load or restore whose target session platform differs from the recorded one, without mutating the target
- [x] 7.10 Replace the DragnCards JSON paths compiled into SQL (`state.game.roundNumber`, `state.game.stepId`) with platform-aware projection
- [x] 7.11 Unit and integration tests: two platforms sharing a `game_id` do not collide on seq, lock, or idempotency; a pre-change bundle still imports; a cross-platform restore is refused

## 8. eval-service platform awareness

- [x] 8.1 Write migrations `0004_platform.{postgresql,sqlite}.sql`, adding `platform` to `evaluation_requests` and `evaluated_targets`, widening `uq_targets_game_seq_scope_player`, and joining both `ix_*_game_id`
- [x] 8.2 Resolve platform from the recording; reject a contradicting caller-supplied platform with `422`, and treat unattributable history as `dragncards`
- [x] 8.3 Append platform to the verdict idempotency key **only when it is not the default**, so existing `dragncards` digests stay byte-identical
- [x] 8.4 Test pinning an existing `dragncards` verdict digest against its pre-change value
- [x] 8.5 Make the judge state projection per platform, keeping DragnCards output byte-identical so no evaluator-version bump or re-evaluation is triggered
- [x] 8.6 Make the action taxonomy per platform, keying marvel-lcg options by id plus name plus event, never by name alone
- [x] 8.7 Tell the judge which platform produced the move, and that on a rules-enforcing engine legality was guaranteed so `rules_legality` grades choice quality within the enumerated legal set
- [x] 8.8 Take round scoping from the neutral `playRound` rather than re-deriving DragnCards' `+1`

## 9. agent-orchestrator platform awareness

- [x] 9.1 Derive turn and phase authority from the neutral `phase` classification, removing the hardcoded `PLAYER_PHASE_STEPS`/`VILLAIN_PHASE_STEPS`/`PASSIVE_PHASE_STEPS` step-id sets
- [x] 9.2 Declare the phase-advancing and seat-action tool sets per platform, with an empty phase-advancing set for marvel-lcg
- [x] 9.3 Treat `pendingSeats` as turn authority on a platform that reports it, recording an illegal-action finding for a seat acting while absent from it
- [x] 9.4 Stop inferring seat ownership from the DragnCards group-name shape; use normalised zone ownership where the platform provides no group names
- [x] 9.5 Make the system prompt name the session's platform, preserving the existing DragnCards wording exactly so `test_runtime_helpers.py:32` stays green
- [x] 9.6 Unit tests: DragnCards guard conclusions are unchanged for every step id, and a marvel-lcg seat is never found in violation through a tool that platform lacks

## 10. Dashboard

- [x] 10.1 Carry `platform` on the games list model and surface it per row
- [x] 10.2 Replace the single DragnCards iframe with a per-platform viewer resolver, keeping the existing `/room/<slug>` template as the DragnCards case and its single-source rule
- [x] 10.3 Address marvel-lcg as read-only `/watch` by default, and `/?p=<seat-1>` only when a seat is deliberately taken
- [x] 10.4 Add `MARVEL_LCG_BASE_URL` to the dashboard config and to `vitest.setup.ts`, which clears every variable the config reads
- [x] 10.5 Keep game platforms out of `SERVICE_KEYS`, so no platform is proxied and `/api/proxy/marvel-lcg/debug` cannot exist
- [x] 10.6 Make the history round and phase mapping per platform: DragnCards keeps its `+1` and dotted step table; marvel-lcg's round is displayed as-is and its integer step id is never looked up in the step table
- [x] 10.7 Render the transcript phase chip from the platform-appropriate label
- [x] 10.8 Scope board reconstruction and restore per platform, and where a platform supports no state import, disable the control with a stated reason rather than building a room on the platform we can reach
- [x] 10.9 Tests: no resolved viewer URL carries `/debug` or a `debug`/`show`/`replay` parameter; a marvel-lcg first player turn is not labelled "Round 2"

## 11. Skill corpus

- [x] 11.1 Leave `marvel-champions-rules-reference` and `marvel-champions-learn-to-play` untouched, and add a test asserting they contain no platform tokens
- [x] 11.2 Split `marvel-champions-play` into a platform-neutral `SKILL.md` plus per-platform harness references
- [x] 11.3 Move the DragnCards group-id catalogue and its harness quirks into a DragnCards harness reference
- [x] 11.4 Add a marvel-lcg harness reference covering the enumerated-option surface, choosing by option id, and the target-range rules
- [x] 11.5 Move the orchestrator round loop's authoritative tool list into one reference per platform
- [x] 11.6 Add `skills/marvel-lcg/` as the platform-build skill beside `skills/dragncards/`, including its hazard list
- [x] 11.7 Update the `DRAGNCARDSAI_REALITY.md` preface in every skill to account for more than one platform
- [x] 11.8 Rebuild the agent-orchestrator and eval-service images, since skills are `COPY`-ed rather than bind-mounted, and confirm the new skill is discovered

## 12. Documentation and repository consistency

- [x] 12.1 Update `README.md`: the service URL table, the architecture diagram, the prose, and the marvel-lcg attribution and licensing note
- [x] 12.2 Update `AGENTS.md`: Useful Reading, the port list, the create-a-game recipe, and the state vocabulary
- [x] 12.3 Update `openspec/config.yaml`, whose `context:` block hardcodes the DragnCards architecture, the Phoenix wire format, and the DragnLang action list
- [x] 12.4 Add a `services/game-service/AGENTS.md` note on the driver seam and on which facts are platform-specific
- [x] 12.5 Credit the Irefrixs Team wherever the integration is documented, and record that card art is never redistributed

## 13. Pre-existing spec defects found while doing this work

- [x] 13.1 Fix `openspec/specs/game-service/spec.md` requirement 42, whose opening line wraps before its `SHALL`, by reflowing that one line
- [x] 13.2 Add the missing `## Purpose` section to `openspec/specs/typed-game-actions/spec.md`
- [x] 13.3 Correct `AGENTS.md:452-454`, which states one pre-existing `openspec validate --all` failure when clean `main` has two, to state the expected count after these fixes

## 14. Checks and verification

> Verification note: the eval SQLite StaticPool concurrency fixture is pre-existing flaky (98/100 focused repetitions passed); its PostgreSQL integration coverage passed.

- [x] 14.1 `./scripts/lint.sh --fix` clean
- [x] 14.2 `./scripts/test.sh unit` green, with test counts recorded before and after
- [x] 14.3 `./scripts/docker-infrastructure.sh start` then `./scripts/test.sh integration` green for both platforms
- [x] 14.4 `openspec validate --all` reports zero failures once tasks 13.1 and 13.2 land
- [x] 14.5 Drive a DragnCards game end-to-end in the running app and confirm no regression
- [x] 14.6 Drive a marvel-lcg game end-to-end in the running app through the dashboard, and record what was and was not exercised
- [x] 14.7 Run `/code-review`, `/security-review` and `/simplify`, and address the findings
- [x] 14.8 Archive the change and sync `openspec/specs/`
