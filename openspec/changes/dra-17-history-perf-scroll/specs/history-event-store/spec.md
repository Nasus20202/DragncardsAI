## ADDED Requirements

### Requirement: Timeline read that omits unbounded payload fields

The history-service SHALL expose a read API that lists a game's events **without
the payload fields whose size is unbounded**, so that listing a whole game's
timeline costs a size proportional to the number of events rather than to the size
of the recorded game states.

The omitted fields SHALL be `state` — the raw DragnCards room state, measured on
real recorded games at ~450-470 KB per `game-service` event — and
`conversation_context`, an agent move's whole captured conversation. Every other
payload field SHALL be carried through verbatim.

`state` SHALL NOT simply vanish: the entry's payload SHALL carry a projection of
it under `state.game` holding `roundNumber` and `stepId`, which is what a
consumer needs to label the round and the phase. The projection SHALL preserve
the recorded types — `stepId` is a dotted Marvel Champions step id and SHALL
remain a string, so step `0.1` SHALL NOT be reported as the number `0.1`, and
`roundNumber` 0 SHALL be reported as 0 rather than as absent, because 0 is the
whole first round of play. Where no game state was recorded for an event, no
`state` projection SHALL be present.

Each entry SHALL declare that its payload is reduced, so a consumer can tell a
timeline entry from a complete event and knows to fetch the complete event before
displaying an omitted field. The complete payload SHALL remain reachable per event
through the existing events read.

The timeline read SHALL use the same cursor contract as the events read — an
`after_seq` request parameter, ascending `seq` order, and a `next_after_seq`
response cursor that is absent once the log is exhausted — so a client walks
either one the same way. Its per-request `limit` ceiling MAY be higher than the
events read's, because an entry is orders of magnitude smaller.

The omitted fields SHALL be removed by the database rather than in the service
process, so that they are neither deserialized nor re-serialized on the way out.

The events read, its `limit` ceiling, its response shape, the games listing, the
snapshots read and restore SHALL be unchanged by this requirement.

#### Scenario: A listed entry drops the recorded state's bulk but keeps its round and step

- **WHEN** a client requests a game's timeline and the game has `game-service` events carrying a full DragnCards room state
- **THEN** each entry's payload SHALL omit the state's card definitions, group and stack tables, and delta log, and SHALL carry `state.game.roundNumber` and `state.game.stepId`

#### Scenario: A dotted step id survives as a string

- **WHEN** a listed entry's recorded step id is `0.0` or `0.1`
- **THEN** the timeline read SHALL report it as the string `"0.0"` or `"0.1"` and SHALL NOT report it as a number

#### Scenario: A listed agent entry drops the conversation but keeps the decision

- **WHEN** a client requests a game's timeline and the game has `agent` events carrying a captured conversation
- **THEN** each such entry's payload SHALL omit `conversation_context` and SHALL carry the move's intended action, reasoning, and arguments

#### Scenario: A listed entry is far smaller than the same event read in full

- **WHEN** the same game is read through the timeline read and through the events read
- **THEN** the timeline response SHALL be at least an order of magnitude smaller than the events response

#### Scenario: An entry declares that its payload is reduced

- **WHEN** a client reads an entry from the timeline read
- **THEN** the entry SHALL indicate that its payload is not complete, and an event read from the events read SHALL NOT so indicate

#### Scenario: The timeline pages with the events read's cursor

- **WHEN** a client walks a game's timeline by passing each response's `next_after_seq` as the next request's `after_seq`
- **THEN** the history-service SHALL return the events in ascending `seq` with no gaps and no repeats, and SHALL omit the cursor from the page that exhausts the log

#### Scenario: A complete payload is still reachable for one event

- **WHEN** a client holds a timeline entry and needs the payload fields the listing omitted
- **THEN** the existing events read SHALL serve that single event with its payload intact

#### Scenario: Timeline of an unknown game

- **WHEN** a client requests the timeline for a `game_id` with no stored history
- **THEN** the history-service SHALL return an empty result rather than an error
