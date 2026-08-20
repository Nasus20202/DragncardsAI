# Design: marvel-lcg as a second game platform

## Context

DragncardsAI plays Marvel Champions on DragnCards. DragnCards is a *playtable*: it moves cards,
runs plugin automation, and accepts whatever the client pushes. It does not adjudicate rules and
cannot say which moves are legal.

`marvel-lcg` is a *rules engine*. Its server is Python + aiohttp, its client is a thin
TypeScript page, and the two talk over plain HTTP+JSON. It refuses illegal input and enumerates
the legal move set on request. It was open-sourced 2026-07-27 and sunset 2026-07-31; the
maintained `z00lus` "Ronin Edition" fork adds a working Dockerfile and Linux packaging.

The integration was verified before this design was written: the fork was built with its own
compose file and driven headlessly to create a Rhino vs Spider-Man solo game, resolve the
mulligan prompt, and flip Peter Parker to hero form, choosing from enumerated legal options each
time. The observations from that run are load-bearing here and are called out as **verified**.

Our side has no platform seam. `GameSession`/`SessionManager` are typed on
`PhoenixClient`/`Channel`/`PhoenixRoom`; `translate_action` is one `isinstance` chain;
`api/enums.py` builds `GroupId`/`LayoutId` at *import time* from Marvel Champions plugin JSON, so
the OpenAPI document and every MCP tool schema depend on one platform's files existing on disk.
Downstream, `game_id` is a single flat keyspace behind every unique constraint, sequence series,
advisory lock and idempotency key, and no `platform` discriminator exists anywhere.

## Goals / Non-Goals

**Goals**

- One game-service that drives either platform behind a single driver protocol.
- An agent that reads *one* normalised game-state shape regardless of platform.
- On marvel-lcg, the agent chooses from engine-validated legal moves, so illegal moves are
  impossible by construction.
- Every recorded event, snapshot and evaluation is attributable to the platform that produced it,
  with existing DragnCards data unchanged.
- The Marvel Champions rules corpus stays platform-neutral and shared.

**Non-Goals**

- Feature parity between platforms. Each keeps its own move surface.
- Cross-platform game migration, snapshot portability, or replaying a DragnCards game on
  marvel-lcg.
- A general plugin system for N platforms. Two implementations of one protocol, not a registry.
- Modifying either upstream, running marvel-lcg's Windows binary, loading third-party card
  scripts, or exposing `/debug`.

## Decisions

### Decision 1: One game-service with a `GamePlatform` driver protocol

game-service keeps ownership of sessions, the HTTP/MCP surface, history emission and snapshots.
Platform-specific behaviour moves behind a `GamePlatform` protocol covering: authenticate,
create table, attach to an existing table, connect, request state, execute a move, seat and
spectator control, and teardown. `PhoenixRoom` becomes `DragnCardsPlatform`; the new driver is
`MarvelLcgPlatform`. `GameSession` holds a driver instead of a concrete client, and stops both
constructing DragnCards payloads and grepping DragnCards log messages for errors.

*Alternatives considered.* **A second service (`marvel-lcg-service`)** — rejected: it would
duplicate session management, the session store, history emission, snapshotting and the MCP
surface, and the agent-orchestrator hardcodes one privileged MCP registry row named
`game-service`, so a sibling service would need a second privileged path through prompt
assembly, the seat guard and the turn guard. **An adapter inside agent-orchestrator** — rejected:
the orchestrator is LLM plumbing; giving it a game transport puts protocol retry logic next to
prompt assembly and leaves history-service unable to restore a marvel-lcg game. **Driving
marvel-lcg's web UI with Playwright** — rejected: the page is a thin client over the same
endpoints, so browser automation adds a browser, a renderer and flakiness for nothing.

### Decision 2: `platform` is a first-class discriminator, defaulting to `dragncards`

A short slug (`dragncards`, `marvel-lcg`) is carried on session metadata, on the history event
envelope, as a real column on `events`/`snapshots`/`evaluation_requests`/`evaluated_targets`, in
the export-bundle header, and on the dashboard's game rows. It is joined into every unique
constraint and index that today keys on `game_id` alone, and into the eval verdict idempotency
key. Existing rows default to `dragncards` via a `NOT NULL DEFAULT` so no backfill is needed and
no existing behaviour changes.

*Alternatives considered.* **Infer platform from `plugin_name`** — rejected: `plugin_name` and the
numeric `plugin_id` are DragnCards concepts (a row in DragnCards' own plugin table); marvel-lcg
has no plugin notion, so the field would have to carry a lie. **Keep it inside `payload_json`
only** — rejected: `EventEnvelope` allows extra keys but the commit path enumerates columns
explicitly, so a payload-only field is silently discarded, cannot be indexed, and cannot
participate in the unique constraints that actually need it. **A separate database or schema per
platform** — rejected: the history and eval APIs are per-game, cross-platform listing and
comparison is a goal, and two schemas double the migration surface for no isolation we need.

### Decision 3: marvel-lcg exposes enumerated legal options, not typed actions

marvel-lcg's `GET /get_ask` returns each available effect with its id, name, legal target ids,
target-count range, payment options and selection rule. The agent surface mirrors that: list the
pending options for a seat, and submit a choice as `{id, targets, resources}`. These options are
**not** mapped onto the 25 DragnCards typed actions.

Two consequences must be handled rather than wished away. **Verified: option `name` is not
unique** — a single prompt returned three options, two of them named `Play`, distinguishable only
by `id`. The option list handed to an agent is therefore keyed by `id` and enriched with the
target cards' names and types resolved from the world payload, otherwise the choice is not
expressible. **Verified: `range=[0,0]` means the option takes no targets even when
`all_legal_targets` is non-empty**, so the target list must be ignored in that case.

*Alternatives considered.* **Translate options into the existing typed actions** — rejected: the
mapping is lossy and fragile (there is no `Change_Form` or "resolve mulligans with this subset of
6 cards" typed action), and it discards the one property that makes this platform valuable, the
legal-move guarantee. **Expose marvel-lcg's raw `AskOptionPayload` unchanged** — rejected: it
leaks `options_json` as a nested JSON string, unnormalised prompt text with decorative newlines,
and bare integer card ids the agent cannot interpret.

### Decision 4: a per-platform normaliser below `GameSession`, one neutral state shape

State normalisation moves out of `api/routers/game_state.py` and below `GameSession`, into a
`StateNormaliser` per platform. Agents keep reading one `SimplifiedGameState`. The four
`plugin_name == "marvel-champions"` string branches collapse into one polymorphic call.

The neutral shape must be widened carefully, because **verified: marvel-lcg's vocabulary does not
correspond to DragnCards'**. Its `phase` is human prose (`"Player 1 Turn"`, `"Resolve
Mulligans"`), not a dotted step id; its `current_step_id` is a monotonic integer with no relation
to DragnCards' `"1.1"`/`"2.3"`; and its `round_id` is already the *play* round (0 during setup, 1
on the first player turn), whereas DragnCards' `roundNumber` counts *completed* rounds and needs
`+1`. So the neutral model carries a play-round number and an opaque per-platform phase label
plus a neutral phase classification, and each platform's normaliser is the only place that
conversion lives. The `+1` convention, currently duplicated across seven Python modules, three TS
modules and five spec files, must not be re-encoded downstream.

Zones are mapped by meaning, not by name: marvel-lcg's `hand_cards`/`player_deck`/`area_hero`/
`engaged_enemies`/`area_villain`/`area_schemes_main` project onto the same neutral zones
DragnCards' `playerNHand`/`playerNDeck`/`playerNPlay1`/`playerNEngaged`/`sharedVillain`/
`sharedMainScheme` project onto. marvel-lcg's per-seat visibility model
(`visible_for_players`, `is_face_up`, `down_card_ids`) is honoured: a seat sees exactly what that
seat's human would, and hidden cards collapse to the existing `HIDDEN` form.

*Alternatives considered.* **Expose each platform's raw state and let skills branch** — rejected:
every skill, the eval projection and the dashboard round model would fork, which is the coupling
we are removing. **Force marvel-lcg into DragnCards' group ids and dotted step ids** — rejected:
it invents a fake `stepId` and a fake completed-round counter, and any consumer that trusted them
would be wrong.

### Decision 5: seats are neutral `player1..player4`, mapped to marvel-lcg's `p=0..3`

The repository's seat vocabulary (`player1..player4`, `SEAT_IDS`, the orchestrator's
`^player[1-4]$`, eval's `player` column) is kept as the neutral model. The marvel-lcg driver maps
`playerN` to `p=N-1` at the transport edge only. **Verified: a bot is protocol-indistinguishable
from a remote human** — a human can hold `?p=0` in a browser while the bot drives `?p=1` against
the same server, which is exactly the mixed-seat mode the dashboard already models.

*Alternatives considered.* **Adopt zero-based seats everywhere** — rejected: it would rewrite the
orchestrator seat guard, eval's `player` column values, the dashboard roster and every skill for
cosmetic gain, and silently re-key existing eval verdicts. **Expose marvel-lcg's `hot_seat` mode
as a seat** — rejected: it is a single-client convenience that breaks the per-seat visibility
model we depend on for fair play.

### Decision 6: vendor the Ronin fork as a submodule; run it from our own compose service

`external/marvel-lcg` is a git submodule pinned to a `z00lus/marvel-lcg` commit. We add
`external/docker/marvel-lcg/` with our own compose service and Dockerfile derived from the fork's,
rather than including the fork's `docker-compose.yml`: ours must join the existing
`dragncards-shared` network, take its published port from `${MARVEL_LCG_PORT:-4006}`, set a
password, and be selectable by compose profile so `docker compose up` does not force both
platforms. **Verified: the fork's own `launch.json` binds `0.0.0.0`, not loopback** — with an
unauthenticated `/debug` reaching `exec()` behind a bypassable AST blocklist, this is the single
most important thing to get right. See Risks.

*Alternatives considered.* **Include the fork's `docker-compose.yml` directly** — rejected: it
declares its own container name, publishes 2345 unconditionally, mounts host paths relative to the
submodule, and joins no shared network. **Install it as a Python dependency** — not possible; it
is not packaged. **Expect the developer to run it on the host** — rejected: CI needs a
reproducible instance and the integration suite must be able to create games.

### Decision 7: the driver caps its own retries and detects stuck prompts

marvel-lcg's engine retries invalid input **forever** with no cap, backoff or logging (issue #5,
won't-fix; a reporter measured 459,505 calls in 90s). `POST /post` always returns `200` with an
empty body and silently drops input when the seat is not being asked. So the driver owns liveness:
a bounded number of submission attempts per prompt, and stuck-state detection that fails loudly.

**Verified: the naive detector does not work.** The ask frame *repeats* the previous `render_id`
(`render_id=30 ask=[]` was followed by `render_id=30 ask=[0]`), so "watch `render_id` advance"
gives false positives. Stuck detection keys on the tuple of `(render_id, ask_players,
prompt_text, option ids)` recurring after a submission. **Verified: frames arrive per engine step
and are very frequent** — 35 frames during setup before the first prompt — so the driver
coalesces frames and emits history events on prompts and completed moves, never per frame.

*Alternatives considered.* **Patch the engine** — rejected: we do not modify upstreams, and the
fix exists only on an unmerged branch of a third fork. **Rely on the `timeout` field** — rejected:
`max_timeout` defaults to 0 (wait forever) and the documented multiplayer default contradicts it;
the timer is not a liveness guarantee.

### Decision 8: create the game, then connect, then play

**Verified ordering constraint:** `GET /new` alone does not start anything. The engine only
advances while a client is attached to `WS /ws`; until the socket connects and sends `Connected …`
the world stays empty (`render_id=0`, `players: []`, `phase: ""`). The driver's session bring-up
is therefore strictly: authenticate → fetch the version cookie → create the game → open the
socket → send `Connected` → wait for the first frame carrying our seat in `ask_players`.

Two further verified transport facts belong in the driver, not in a comment: game setup embeds
**stringified JSON content**, not paths (`campaign_json` is the scenario document's text and
`hero_json` is a list of deck document texts, fetched from `/get_scenario_json` and
`/get_hero_json` first); and an aiohttp client **silently drops cookies for IP-address hosts**
unless its jar is constructed unsafe, which manifests as a WebSocket handshake failing with
`200 Invalid response status` rather than as an auth error. We connect by container hostname and
assert `Content-Type` on every response so this class of failure is loud.

### Decision 9: lazy, per-platform enum generation

`api/enums.py` must stop calling `plugin_metadata.load_groups()` at module import. Group and
layout vocabularies become per-platform and lazily resolved, so the service imports and serves
its OpenAPI document with no platform's plugin JSON on disk. This is a prerequisite for
marvel-lcg, which has no groups, no layouts and no plugin JSON at all.

*Alternatives considered.* **Keep import-time literals and ship marvel-lcg placeholder plugin
JSON** — rejected: it fabricates a group vocabulary marvel-lcg does not have, and leaves the
OpenAPI document a function of files on disk. **Widen the literals to a plain `str`** — rejected:
it loses the schema-level validation the MCP tool surface depends on for DragnCards.

### Decision 10: the rules corpus stays shared; only the harness layer splits

The ~5,400 lines under `marvel-champions-rules-reference` and `marvel-champions-learn-to-play`
contain zero platform tokens and are not touched. The ~1,600 lines of harness contract in
`marvel-champions-play` and `marvel-champions-orchestrator/references/round-loop.md` split into a
platform-neutral skill plus per-platform harness references, and a new `skills/marvel-lcg/` joins
`skills/dragncards/` as the platform-build skill. Because skills are `COPY`-ed into the
agent-orchestrator and eval-service images rather than bind-mounted, any skill change requires an
image rebuild — the tasks must say so.

*Alternatives considered.* **Duplicate the whole corpus per platform** — rejected: it doubles
7,700 lines and guarantees the rules text diverges. **One skill with in-line platform
conditionals** — rejected: the play skill's authority comes from being unambiguous, and "if
DragnCards, else marvel-lcg" prose in every recipe destroys that.

## Risks / Trade-offs

- **`marvel-lcg` has no LICENSE file.** All-rights-reserved by default, on top of unlicensed
  Marvel/FFG intellectual property. We rely on the developer's explicit written permission in
  `irefrixs/marvel-lcg` issue #3, credit the Irefrixs Team, and never redistribute card art (it
  streams at runtime from Cerebro). This is a known, accepted risk, not an oversight.
- **The project is sunset and we depend on a fork.** No upstream PRs are accepted. Mitigation: pin
  the submodule to a commit; the upside of a sunset project is that the HTTP surface is frozen —
  the developer had previously refused to open-source precisely because the core API kept changing.
- **`GET /debug` is unauthenticated arbitrary code execution**, dev-acknowledged won't-fix, and the
  vendored fork binds `0.0.0.0`. Mitigations, all required: the container joins only the internal
  network, a password is set, no host port is published outside development, and `/debug` is never
  reachable through the dashboard proxy or any game-service route. This is the highest-severity
  item in the change and it must be verified by a test, not by inspection.
- **The unbounded input-retry loop can spin the engine at thousands of calls per second** if our
  driver submits input the engine rejects. Decision 7 is the mitigation; without a cap a single
  malformed submission is a self-inflicted denial of service.
- **RNG non-determinism** (issue #4): numpy and the bundled Mersenne Twister produce different
  sequences from the same seed and the scene does not record which was used, so replays can
  diverge. Mitigation: keep numpy installed, never set `disable_numpy_random`, and do not promise
  seed-reproducible replays for marvel-lcg.
- **The riskiest change on our side is Decision 9.** Making `GroupId`/`LayoutId` lazy alters the
  OpenAPI document, and therefore every MCP tool schema, for DragnCards too. `test_mcp_server.py`,
  `test_app_strict_request_bodies.py` and `test_capabilities.py` pin those surfaces and must stay
  green unchanged; any diff in the DragnCards tool schemas is a regression, not an update.
- **Widening unique constraints on a live table.** The history and eval migrations drop and
  recreate constraints. The shared migration runner splits statements on a naive `;`, so neither
  migration may contain a semicolon inside a string literal or a `DO $$ … $$` block, and SQLite
  needs the table-rebuild pattern already used by `eval-service` `0002_target_player`.
- **Re-keying eval verdicts.** Adding `platform` to the verdict idempotency key changes the digest
  for every existing verdict. Mitigation: keep the key's existing field order and append, and
  treat absent platform as `dragncards` so previously written digests still match.
- **No upstream protocol documentation exists.** Our understanding comes from reading the source
  and from the verified run recorded above. Anything we did not exercise — multi-hero games,
  campaign mode, `/continue_game`, the fork's server-side MarvelCDB sync — is unverified and must
  be treated as such in the tasks.

## Migration

1. Additive, defaulted columns first: history `0002` and eval `0004`, each in both PostgreSQL and
   SQLite dialects. Existing rows become `platform = 'dragncards'` with no backfill step.
2. `platform` becomes optional on the wire with a `dragncards` default, so an older producer and a
   newer consumer interoperate during a rolling restart, and an export bundle written before this
   change still imports.
3. game-service refactors behind the driver protocol with DragnCards as the only implementation
   and no behaviour change, proven by the existing suite passing untouched, before the marvel-lcg
   driver is added.
4. The submodule and its compose service land behind a profile, so an existing checkout that does
   not initialise the new submodule still runs the DragnCards stack.
5. No data migration is needed for the skill corpus, but the agent-orchestrator and eval-service
   images must be rebuilt for skill changes to take effect.
