# marvel-lcg Specification

## Purpose
The marvel-lcg capability integrates the rules-enforcing Marvel Champions engine with the
platform-neutral game-service driver, preserving authenticated setup, per-seat visibility,
enumerated legal options, and bounded render progress.

## Requirements

### Requirement: Password authentication and the version-cookie gate

marvel-lcg SHALL expose `POST /authenticate`, which takes `{"password": "<password>"}` and sets a
`session_token` cookie whose value is the MD5 digest of the configured password. It SHALL treat a
request as authenticated when no password is configured, and otherwise when the request's
`session_token` cookie equals that digest. Our client SHALL either call `POST /authenticate` or send
`Cookie: session_token=<md5(password)>` on every request, and SHALL be configured against an engine
that has a password set.

marvel-lcg SHALL apply a second, independent gate: a request SHALL be served only when it carries an
`app_version` cookie matching the running build. `GET /get_version` SHALL be reachable without either
gate, SHALL respond `200` with content type `image/jpeg`, and SHALL set the `app_version` cookie. Our
client SHALL fetch it before any other call.

Both gates fail open into HTML: a request missing either cookie SHALL be answered with an
authentication or cache-clearing page as `text/html` with **HTTP 200**, not with an error status. Our
client SHALL therefore assert the `Content-Type` of every response before parsing it, and SHALL treat
an HTML body as an authentication failure rather than as a malformed payload. Our client SHALL also
ensure cookies are actually transmitted for the host it connects to — a client that silently drops
cookies for a bare IP address host surfaces this failure as a WebSocket handshake rejected with
`200 Invalid response status`, which names neither cookies nor authentication.

#### Scenario: The version cookie is fetched before anything else
- **WHEN** our client begins a marvel-lcg session
- **THEN** it SHALL send `GET /get_version` before any other request
- **AND** it SHALL retain the `app_version` cookie that response sets for every subsequent request and for the WebSocket handshake

#### Scenario: An HTML body with status 200 is treated as an authentication failure
- **WHEN** a request is made without a required cookie and the engine answers `200` with `Content-Type: text/html`
- **THEN** our client SHALL fail that call as an authentication failure naming the missing gate
- **AND** SHALL NOT attempt to parse the body as JSON

#### Scenario: Content type is asserted on every response
- **WHEN** our client receives any response from marvel-lcg
- **THEN** it SHALL assert the response's `Content-Type` against the type that endpoint is contracted to return before reading the body

#### Scenario: Cookies are transmitted for the configured host
- **WHEN** our client is configured with a marvel-lcg address and opens the render-frame WebSocket
- **THEN** the handshake request SHALL carry the `app_version` and `session_token` cookies
- **AND** the client SHALL be configured by container hostname rather than by bare IP address, so cookie handling is not silently skipped

### Requirement: Game creation embeds document content, not file paths

marvel-lcg SHALL create a game entirely over HTTP through `GET /new?data=<NewGameDescriptor>`,
where the descriptor contains stringified scenario and hero-deck document content. The
game-service driver SHALL accept only scenario and hero-deck ids returned by the neutral setup
catalog, resolve those ids to document content immediately before creation, and preserve the
ordered `hero_decks` list when constructing `hero_json`.

The driver SHALL derive catalog identity from the engine document's logical relative path. Equivalent
representations that differ only by a leading `./` SHALL identify the same document for catalog
membership checks, so an opaque id returned by setup discovery SHALL remain valid if the engine
uses the equivalent spelling in the immediately subsequent listing. The driver SHALL retain the
actual path returned by the live creation listing when fetching the document.

The driver SHALL not accept a display name, an arbitrary filesystem path, a MarvelCDB import, or an
untyped `plugin_info` mapping as an alternative setup identity. If a selected id is no longer in the
live catalog, creation SHALL fail rather than selecting another entry.

#### Scenario: Selected catalog ids become document content

- **WHEN** a caller selects one listed scenario id and two listed hero-deck ids in seat order
- **THEN** the driver SHALL fetch the corresponding scenario and deck documents
- **AND** SHALL send those document texts in the descriptor in the same order

#### Scenario: Equivalent engine path spellings preserve a selected hero-deck id

- **WHEN** setup discovery returns `./deck/starter/spider_man.json` and creation's live listing returns
  the same document as `deck/starter/spider_man.json`
- **THEN** the opaque id returned by setup discovery SHALL be accepted by creation
- **AND** the driver SHALL fetch the path from the live creation listing
- **AND** the driver SHALL send Spider-Man's document content in the new-game descriptor

#### Scenario: A solo game is created from fetched document content

- **WHEN** our client creates a solo game from one listed scenario id and one listed hero-deck id
- **THEN** it SHALL fetch both document contents before calling `GET /new`
- **AND** it SHALL send the scenario text as `campaign_json` and a one-item ordered `hero_json`
  list
- **AND** the engine SHALL answer `200` with `{"result": "New game created"}`

#### Scenario: A descriptor carrying a path instead of content is a client defect

- **WHEN** a descriptor is constructed with a filesystem path rather than fetched document text
- **THEN** the client SHALL fail that construction before sending it
- **AND** it SHALL not rely on the engine to interpret the path

#### Scenario: An invalid descriptor is reported by status

- **WHEN** the engine rejects a descriptor
- **THEN** it SHALL answer `400` with an `error` field, or `409` when campaign progression
  conflicts
- **AND** the client SHALL surface that status as a creation failure rather than retrying blindly

#### Scenario: Only vendored decks and scenarios are used

- **WHEN** the client lists setup data for a game
- **THEN** the listings SHALL come from the vendored engine's scenario and starter-deck catalog
- **AND** the client SHALL not call a MarvelCDB import or sync path

#### Scenario: A stale catalog id is rejected

- **WHEN** a caller submits an id that was listed earlier but is absent during creation
- **THEN** the driver SHALL report that id as unavailable
- **AND** SHALL not send a descriptor containing a different scenario or deck

#### Scenario: A path or display name is not a setup identity

- **WHEN** a caller supplies an engine path or display name instead of a catalog id
- **THEN** the game-service SHALL refuse the request before `GET /new`
- **AND** SHALL direct the caller to `list_game_setup_catalog`

### Requirement: Bring-up order is create, then connect, then play

Creating a game SHALL NOT start the engine. Until a client is attached to the render-frame WebSocket
and has sent the connect message, the world SHALL remain empty — render identifier zero, no players
and an empty phase — and no prompt SHALL be raised. Our client's session bring-up SHALL therefore be
strictly ordered: authenticate, fetch the version cookie, create the game, open the socket, send the
connect message, and only then wait for the first frame that names one of our seats as being asked.

Our client SHALL NOT report a session as ready on a successful `GET /new` alone, and SHALL NOT poll
for state or options before the socket is connected, because the engine advances only while a client
is attached.

#### Scenario: A created game does not start on its own
- **WHEN** our client creates a game and reads the world before opening the socket
- **THEN** the world SHALL report render identifier zero, no players, and an empty phase
- **AND** `GET /get_ask` SHALL return an empty object

#### Scenario: The engine advances once the socket connects
- **WHEN** our client opens the render-frame socket and sends the connect message
- **THEN** the engine SHALL begin pushing frames and SHALL proceed to the first prompt
- **AND** our client SHALL report the session ready only after that first frame arrives

#### Scenario: Bring-up order is enforced by the driver
- **WHEN** our client is asked to execute a move on a session whose socket is not connected
- **THEN** it SHALL refuse the move with a descriptive error
- **AND** SHALL NOT submit anything to the engine

### Requirement: The render-frame WebSocket carries state notifications only

marvel-lcg SHALL expose `WS /ws?p=<seat>` and SHALL push a frame on it whenever the engine's state
changes. Our client SHALL open the socket for the seats the session holds and SHALL send a text
message beginning with `Connected` to trigger the first push; the engine SHALL handle no other
client-to-server message except a mouse-position report. No game move SHALL be submitted over this
socket.

Each pushed frame SHALL carry `render_id`, `game_id`, `ask_players`, `remaining_time`, `max_timeout`,
`notify_texts`, `debug_message`, `current_step_id`, `max_replay_step_id`, `player_id` and
`total_players`. `ask_players` SHALL name the seats whose decision is pending and SHALL be the whole
of the turn protocol: our client SHALL act for a seat when, and only when, that seat appears in
`ask_players`. A `render_id` of `-1` SHALL mean the game is over. Each entry of `notify_texts` SHALL
be a JSON string requiring a second parse.

Our client SHALL NOT rely on `remaining_time` or `max_timeout` as a liveness guarantee, because the
engine's default timeout waits forever.

#### Scenario: The connect message triggers the first frame
- **WHEN** our client opens `WS /ws?p=0` and sends a text message beginning with `Connected`
- **THEN** the engine SHALL push a frame carrying the fields of the frame descriptor

#### Scenario: A seat acts only when it is asked
- **WHEN** a frame arrives whose `ask_players` does not contain a seat our session holds
- **THEN** our client SHALL NOT read options or submit a move for that seat

#### Scenario: Game over is recognised from the frame
- **WHEN** a frame arrives with `render_id` equal to `-1`
- **THEN** our client SHALL treat the game as over, stop submitting moves, and report the terminal status

#### Scenario: Notification entries are parsed twice
- **WHEN** a frame carries `notify_texts`
- **THEN** our client SHALL parse each entry as a JSON document in its own right before reading its fields

#### Scenario: No move is sent over the socket
- **WHEN** our client submits a move
- **THEN** it SHALL use the HTTP submission endpoint
- **AND** SHALL send nothing but the connect message over the WebSocket

### Requirement: Seats are addressed by a zero-based query parameter

marvel-lcg SHALL address seats through a `p` query parameter on the WebSocket, the world read, the
option read, the submission endpoint and the acknowledgement, with values `0` through `3`. Our client
SHALL map the neutral seat identifier `playerN` to `p=N-1` at this edge only, and that mapping SHALL
be the only place the zero-based form appears.

Our client SHALL address exactly one seat on submission, because the engine's submission handler
accepts a single seat. Our client SHALL NOT use the engine's all-seats convenience mode, the cheat or
show modes, or the replay mode, because each of them defeats the per-seat visibility the system
depends on for fair play.

A client driving a seat over HTTP SHALL be indistinguishable to the engine from a human driving
another seat in a browser against the same engine, and our client SHALL rely on that rather than on
any dedicated bot facility.

#### Scenario: A neutral seat is mapped once, at the transport edge
- **WHEN** our client performs any seat-addressed call for `player2`
- **THEN** the request SHALL carry `p=1`
- **AND** the neutral identifier SHALL be what every layer above the driver uses

#### Scenario: Submission addresses exactly one seat
- **WHEN** our client submits a move
- **THEN** the request SHALL name exactly one seat
- **AND** SHALL NOT name a comma-separated seat list

#### Scenario: Visibility-defeating modes are never requested
- **WHEN** any marvel-lcg request is constructed by our client
- **THEN** it SHALL NOT carry the all-seats, cheat, show, or replay query parameters

#### Scenario: A human holds another seat at the same table
- **WHEN** a human plays seat `0` in a browser while our client drives seat `1` against the same engine
- **THEN** both SHALL be served normally
- **AND** each SHALL see only the cards its own seat is permitted to see

### Requirement: World retrieval is per-seat filtered

marvel-lcg SHALL expose `GET /get_world?p=<seat>`, returning the full world descriptor as gzipped
`application/json`. The payload SHALL be filtered by each card's visible-for-seats list, its
face-up flag and its face-down child list, rather than by the query parameter, so a seat sees exactly
what that seat's human player sees.

The world SHALL carry a render identifier, a round identifier, a phase, a prompt, shared zones and a
per-seat list of zones. The phase SHALL be human-readable prose rather than an identifier, the step
identifier SHALL be a monotonically increasing integer bearing no relation to any other platform's
step numbering, the round identifier SHALL already be the play round — zero during setup and one at
the first player turn, needing no adjustment — and a seat's resources SHALL be a string rather than a
count. Our client SHALL treat all four as marvel-lcg's own vocabulary, SHALL convert them only in its
normaliser, and SHALL NOT synthesise a dotted step identifier or a completed-round counter.

Our client SHALL never read a card the world marks as not visible to a seat the session holds into
the agent's context.

#### Scenario: The world is decoded from a gzipped JSON response
- **WHEN** our client sends `GET /get_world?p=0`
- **THEN** the engine SHALL answer gzipped `application/json`
- **AND** our client SHALL assert that content type before decoding

#### Scenario: The round identifier needs no adjustment
- **WHEN** the world reports round identifier one at the first player turn
- **THEN** our client's normaliser SHALL emit play round one
- **AND** SHALL NOT add or subtract an offset

#### Scenario: The phase is carried as an opaque label
- **WHEN** the world reports a phase of `Resolve Mulligans` or `Player 1 Turn`
- **THEN** our client SHALL carry that text as the platform phase label and SHALL derive the neutral phase classification from it
- **AND** SHALL NOT invent a dotted step identifier

#### Scenario: Cards hidden from our seat stay hidden
- **WHEN** the world carries a card whose visible-for-seats list excludes every seat our session holds
- **THEN** our client SHALL collapse that card to the hidden form
- **AND** SHALL NOT place its name or identifier into the agent's context

### Requirement: Option retrieval enumerates the legal move set

marvel-lcg SHALL expose `GET /get_ask?p=<seat>` as the legal-move enumerator. It SHALL return exactly
an empty JSON object when no decision is pending for that seat, and otherwise a gzipped payload
carrying `options_json`, `ability_type`, `event_name`, `prompt_text`, `show_cancel` and
`replay_input`. `options_json` SHALL be a JSON **string** whose parse is the array of options.

Each option SHALL carry `id`, `name`, `bind_id`, an optional bound seat, `all_legal_targets` as card
object identifiers, `target_num_range` as a minimum and maximum, `target_payment` describing each
target's cost and payment effects, `select_rule` with its parameters, required target traits, a
failure reason and a search flag.

Our client SHALL treat `id` as the option's only identity, SHALL treat `target_num_range` as
authoritative over `all_legal_targets`, and SHALL treat `show_cancel` as the only signal that a
cancel or decline is offered for the prompt.

#### Scenario: No pending decision is an empty object
- **WHEN** our client sends `GET /get_ask?p=0` while no decision is pending for that seat
- **THEN** the engine SHALL answer exactly `{}`
- **AND** our client SHALL report no pending options rather than an error

#### Scenario: The option array is parsed out of a nested JSON string
- **WHEN** a pending decision exists
- **THEN** our client SHALL parse `options_json` as a JSON string and then parse its contents as the option array
- **AND** SHALL NOT expose that nested-string form to any caller

#### Scenario: The option identity is its id
- **WHEN** a prompt returns more than one option sharing the same `name`
- **THEN** our client SHALL keep each option distinguishable by its `id`
- **AND** SHALL NOT key, deduplicate, or address an option by its name

#### Scenario: A zero target range overrides the legal-target list
- **WHEN** an option reports `target_num_range` of `[0, 0]` together with a non-empty `all_legal_targets`
- **THEN** our client SHALL treat the option as taking no targets
- **AND** SHALL ignore the legal-target list for that option

### Requirement: Move submission is form-encoded and unacknowledged

marvel-lcg SHALL accept a move at `POST /post?p=<seat>` as an `application/x-www-form-urlencoded`
body whose content is a URL-encoded JSON object of exactly the form
`{"id": <option id>, "targets": [<card object id>, ...], "resources": [<effect id>, ...]}`. An `id`
of `0` SHALL mean decline or cancel.

The endpoint SHALL always answer `200` with an empty body. It SHALL report neither validity nor
application, and SHALL silently discard the input when the addressed seat is not currently being
asked. Our client SHALL therefore never treat the `200` as confirmation that a move was applied, and
SHALL confirm application by observing the engine's subsequent frames and the disappearance of the
prompt.

marvel-lcg SHALL expose `GET /client_updated?p=<seat>&r=<render_id>&g=<game_id>` as the per-seat
render acknowledgement, and our client SHALL send it after processing a frame so the engine knows the
seat is current.

#### Scenario: A move is submitted in the contracted body form
- **WHEN** our client submits option `7` with no targets and no resource payments for seat `player1`
- **THEN** the request SHALL be `POST /post?p=0` with content type `application/x-www-form-urlencoded`
- **AND** the body SHALL be the URL-encoded JSON object `{"id": 7, "targets": [], "resources": []}`

#### Scenario: Declining is submitted as option zero
- **WHEN** our client declines a prompt that offers a cancel
- **THEN** it SHALL submit `id` equal to `0`

#### Scenario: A success status is not treated as confirmation
- **WHEN** the engine answers a submission `200` with an empty body
- **THEN** our client SHALL NOT report the move as applied on that basis alone
- **AND** SHALL confirm application from the engine's subsequent frames and the prompt no longer standing

#### Scenario: The render acknowledgement is sent after processing a frame
- **WHEN** our client has processed a frame for a seat
- **THEN** it SHALL send `GET /client_updated` carrying that seat, the frame's render identifier, and the frame's game identifier

### Requirement: Submission attempts are bounded and stuck prompts are detected

marvel-lcg's engine SHALL be assumed to retry an unsatisfied prompt without limit, backoff, or log
output, so that a single unacceptable submission can drive the engine at thousands of calls per
second. Our client SHALL therefore own liveness itself: it SHALL cap the number of submission
attempts per prompt at a bounded, configured limit, and on exhausting that limit SHALL fail the
operation loudly with an error naming the prompt and the options it tried, rather than continuing to
submit.

Stuck-prompt detection SHALL key on the recurrence, after a submission, of the tuple of render
identifier, asked seats, normalised prompt text and the set of option identifiers. It SHALL NOT key
on the render identifier alone: the frame that raises a prompt repeats the render identifier of the
frame before it, so a stalled render identifier is a normal observation and not evidence of a stuck
prompt.

Our client SHALL treat a prompt that recurs unchanged after a bounded number of distinct submissions
as a stuck state, SHALL stop submitting for that session, and SHALL surface it as a session failure.

#### Scenario: Attempts per prompt are capped
- **WHEN** our client's submissions for one prompt reach the configured attempt limit without the prompt being resolved
- **THEN** our client SHALL stop submitting and SHALL fail the operation with an error naming the prompt and the attempted options

#### Scenario: A repeated render identifier is not by itself a stuck state
- **WHEN** a frame with an empty asked-seat list is followed by a frame carrying the same render identifier and a non-empty asked-seat list
- **THEN** our client SHALL treat that as the prompt being raised normally
- **AND** SHALL NOT report a stuck state

#### Scenario: A recurring prompt tuple is a stuck state
- **WHEN** the tuple of render identifier, asked seats, normalised prompt text, and option identifiers recurs unchanged after the configured number of distinct submissions
- **THEN** our client SHALL declare the session stuck, stop submitting, and surface a session failure

#### Scenario: An empty target list on a prompt that requires targets does not loop
- **WHEN** our client submits an option with an empty target list and the prompt is re-raised unchanged
- **THEN** the attempt cap SHALL apply and our client SHALL fail rather than resubmitting indefinitely

### Requirement: Frames are coalesced and recorded selectively

marvel-lcg SHALL push a frame per engine step, and frames SHALL be assumed to arrive far more often
than a caller cares about — tens of frames during game setup before the first prompt, most of them
naming no asked seat. Our client SHALL coalesce frames, keeping only the latest observed frame per
session between decisions.

Our client SHALL NOT treat each frame as a state change worth recording. It SHALL emit a recorded
history event when a prompt is raised for a seat the session holds, when a submitted move has been
confirmed applied, and when the game reaches a terminal state, and SHALL NOT emit one per frame.

#### Scenario: Setup frames do not become recorded events
- **WHEN** the engine pushes tens of frames during setup, none of them naming an asked seat
- **THEN** our client SHALL coalesce them into the latest observed frame
- **AND** SHALL emit no recorded history event for them

#### Scenario: A prompt and a completed move are recorded
- **WHEN** a prompt is raised for a seat the session holds and our client's submission is then confirmed applied
- **THEN** our client SHALL emit a recorded history event for the prompt and one for the completed move

#### Scenario: The terminal state is recorded once
- **WHEN** a frame reports the game as over
- **THEN** our client SHALL emit exactly one recorded history event carrying the terminal status

### Requirement: The engine's debug endpoint is never reached

marvel-lcg SHALL be treated as exposing `GET /debug` as unauthenticated arbitrary code execution: its
command path reaches an interpreter behind an abstract-syntax-tree blocklist that is bypassable, its
authentication wrapper is inert when no password is configured, and the vendored fork binds every
interface rather than loopback.

Our system SHALL never issue a request to that path, SHALL never expose a route, MCP tool, or
dashboard proxy path that can reach it, and SHALL never accept a caller-supplied path or query that
is forwarded to the engine unvalidated. The engine SHALL be run with a password configured and
attached only to the internal container network, with no host port published beyond what local
development requires.

This SHALL be asserted by a test rather than by inspection.

#### Scenario: No surface of ours reaches the debug path
- **WHEN** our HTTP routes, MCP tool list, and dashboard proxy route table are enumerated
- **THEN** none of them SHALL reach marvel-lcg's `/debug` path

#### Scenario: The client never issues a debug request
- **WHEN** every request our client is capable of issuing is enumerated
- **THEN** none SHALL target `/debug`
- **AND** a test SHALL fail if such a request is introduced

#### Scenario: The engine runs with a password and no public port
- **WHEN** the vendored engine's service definition is inspected
- **THEN** it SHALL configure a password, join only the internal network, and publish no port beyond the local development port

### Requirement: The vendored engine runs without third-party card scripts and with numpy retained

marvel-lcg SHALL be understood to execute card behaviour as Python, so a third-party card pack is
arbitrary code. Our deployment SHALL leave the engine's custom-card configuration unset and SHALL
NOT load any card pack that does not ship in the vendored repository.

The engine's random number generation SHALL keep numpy installed and SHALL NOT disable numpy
randomness, because the engine's saved games are recorded against numpy's sequences while its bundled
generator produces a different sequence from the same seed and the saved game does not record which
was used. Consequently our system SHALL NOT promise seed-reproducible replays for marvel-lcg.

#### Scenario: No third-party card pack is configured
- **WHEN** the vendored engine's configuration is inspected
- **THEN** its custom-card file settings SHALL be unset
- **AND** no card data outside the vendored repository SHALL be mounted or referenced

#### Scenario: numpy randomness stays enabled
- **WHEN** the vendored engine's configuration and dependencies are inspected
- **THEN** numpy SHALL be installed and the setting that disables numpy randomness SHALL be unset

#### Scenario: Seed reproducibility is not promised
- **WHEN** a caller asks whether a marvel-lcg game can be replayed exactly from its seed
- **THEN** our documentation and API SHALL state that it cannot be guaranteed
- **AND** SHALL NOT expose an endpoint or tool that claims a deterministic replay

### Requirement: The vendored Marvel engine has one active game owner

The marvel-lcg driver SHALL declare that one configured engine endpoint supports one active game.
Game-service SHALL own a distributed lease for that endpoint and SHALL not create a second game or
attach an arbitrary session while the lease is held. The driver SHALL not claim that a
service-generated slug is an engine table identifier.

#### Scenario: The engine rejects a second owner

- **WHEN** a second game-service session requests creation against an endpoint with an active
  lease
- **THEN** the request SHALL be refused before `GET /new`
- **AND** the first session's ownership SHALL remain unchanged

#### Scenario: Attach is unsupported without an engine id

- **WHEN** a caller asks the driver to attach to a Marvel slug
- **THEN** the driver SHALL return a descriptive unsupported-attachment error
- **AND** SHALL not open a socket to an unverified active game

### Requirement: Marvel startup is a normal deployment prerequisite

The integration SHALL assume that the repository's ordinary Compose startup starts the engine and
its initialization service. The driver SHALL report a distinct unavailable-backend error when the
engine health or initialization prerequisite is not ready, rather than behaving as if the absence
were an empty setup catalog. The game-service API SHALL map that error to HTTP `503` with a
readiness-oriented `Retry-After` response header.

#### Scenario: A healthy ordinary stack serves setup catalogs

- **WHEN** the ordinary stack reports the Marvel engine and initializer ready
- **THEN** the driver SHALL authenticate and return its scenario and hero-deck catalog
- **AND** setup discovery SHALL not require a profile-specific startup action

#### Scenario: An unready engine is reported distinctly

- **WHEN** Marvel setup discovery runs before the engine initialization prerequisite is ready
- **THEN** the service SHALL report an unavailable-backend error naming the readiness dependency
- **AND** SHALL not report that the catalog is valid but empty

### Requirement: Selected setup is verified before session readiness

The game-service Marvel driver SHALL retain the selected scenario and ordered hero-deck
identities from the fetched catalog documents. Before a newly created session is returned,
it SHALL obtain a ready engine world and verify the selected player count and one matching
hero identity per ordered seat, plus a matching selected scenario villain and main scheme
from the visible world areas or their corresponding decks.

#### Scenario: Selected Rhino setup is returned only after matching validation

- **WHEN** a caller selects a Rhino scenario and an ordered hero-deck list
- **THEN** the driver SHALL return a session only after the first ready world contains the
  selected player identities and Rhino scenario witnesses

#### Scenario: A default or mismatched board is rejected

- **WHEN** the engine returns a world whose player identity, player count, villain, or main
  scheme does not match the selected setup
- **THEN** session creation SHALL fail with a descriptive setup-integrity error
- **AND** SHALL NOT return a session claiming the selected setup

#### Scenario: A malformed ready world is rejected

- **WHEN** the first ready world cannot supply a required selected-setup witness
- **THEN** the driver SHALL fail clearly rather than substitute a catalog entry or accept
  the world as ready

### Requirement: Render acknowledgement is load-bearing and bounded

The Marvel driver SHALL acknowledge each processed non-degraded render frame for its seat
using the frame's render and game identifiers. Acknowledgement failures SHALL retry only a
bounded configured number of times. After exhaustion the driver SHALL mark that seat's
transport degraded, notify the state-unavailable handler, and fail the operation that
requires acknowledged progress with a transport error.

#### Scenario: Empty pending reveal advances after acknowledgement

- **WHEN** the engine sends a frame with `ask_players=[]` while a reveal or setup step is
  in progress
- **THEN** the driver SHALL acknowledge and consume that frame
- **AND** SHALL continue waiting for a later frame that names a held seat
- **AND** SHALL NOT invent or submit an option for the empty pending-seat list

#### Scenario: Acknowledgement failure degrades explicitly

- **WHEN** the engine does not accept a frame acknowledgement within the configured retry
  budget
- **THEN** the driver SHALL stop waiting or submitting for that seat
- **AND** SHALL report render transport degradation instead of hanging indefinitely

#### Scenario: Empty options remain empty

- **WHEN** the engine reports no pending ask for a seat
- **THEN** the driver SHALL return an empty option projection
- **AND** SHALL reject a choice because the seat has no pending decision

### Requirement: Startup fallback cannot replace a requested game

The repository-owned Marvel engine image SHALL disable the upstream fallback that silently
loads the hardcoded Rhino and Spider-Man scene when a configured startup save cannot be
loaded. The image build SHALL apply this hardening as an exact zero-fuzz patch, and a
startup-save failure SHALL remain an explicit engine failure.

#### Scenario: A missing configured startup save fails closed

- **WHEN** the engine is configured to load a startup save and that save is absent or invalid
- **THEN** the engine SHALL fail explicitly
- **AND** SHALL NOT create the hardcoded Rhino versus Spider-Man fallback scene

### Requirement: Explicit state seats are validated before engine access

The Marvel LCG driver SHALL validate an explicit neutral `player_n` against the
session's held seats before checking transport state or calling `GET /get_world`. A
seat not held by the session SHALL be rejected without an engine request. When
`player_n` is omitted, the driver MAY use a held seat only as a transport fallback for
obtaining the engine world; that fallback SHALL not choose the normalized hand reader.

#### Scenario: An unheld seat is rejected before transport

- **WHEN** a session holding only `player1` receives a state request for `player2`
- **THEN** the driver SHALL return a seat error
- **AND** SHALL not call the Marvel engine

#### Scenario: A selected seat reaches the engine

- **WHEN** a session holds `player2` and receives a state request for `player2`
- **THEN** the client SHALL request `GET /get_world?p=1`
- **AND** the normalizer SHALL receive neutral `player_n=player2`

### Requirement: Marvel visibility is normalized per request

The driver SHALL not mutate a shared normalizer's reader seat. Each state projection
SHALL pass its requested seat to normalization, and each history projection SHALL pass
the spectator value. The neutral state vocabulary and existing operation surface SHALL
remain unchanged.

#### Scenario: Reader selection does not persist between calls

- **WHEN** the same Marvel normalizer handles a player-one projection and then a
  player-two projection
- **THEN** the second projection SHALL use only `player_n=player2`
- **AND** the first projection's reader SHALL not remain as shared mutable state
