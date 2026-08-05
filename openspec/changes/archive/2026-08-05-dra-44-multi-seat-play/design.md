# Design: serving four seats from one identity

## Context

The whole design turns on one fact about the upstream backend, so it is worth
stating precisely before any decision rests on it.

An action arrives on the room channel as `game_action` and is dispatched with the
socket's authenticated user id:

```elixir
# room_channel.ex:112-122
def handle_in("game_action", %{"action" => action, "options" => options, ...},
      %{assigns: %{room_slug: room_slug, user_id: user_id}} = socket) do
  GameUIServer.game_action(room_slug, user_id, action, options)
```

That `user_id` is then used for exactly one thing before the action runs:

```elixir
# game_ui_server.ex:220-224
gameui = case user_id && Users.get_user(user_id) do
  nil -> gameui
  user -> put_in(gameui, ["options", "language"], user.language)
end
```

and the acting seat comes from the payload:

```elixir
# game_ui.ex:772-773
game_new = game_old |> put_in(["playerUi"], options["player_ui"])
# variables/PLAYER_N.ex:13-17
if game["playerUi"]["playerN"] == nil do
  raise "Variable $PLAYER_N is undefined."
else game["playerUi"]["playerN"] end
```

There is no path between the two. `GameUI.get_player_n_by_user_id/2` — the reverse
lookup that *could* connect them — is called from two places, both outbound
(`handle_out("gui_update", ...)` and `client_update/2`). `GameUIServer.is_player/2`,
which reads exactly like an authorization check, has no call sites at all.

Everything below follows from that: **identity and seat are orthogonal in
DragnCards, so serving N seats is a payload problem, not an authentication problem.**

## Goals / Non-Goals

**Goals.** Make a two-to-four player Marvel Champions game fully set up and driven
through game-service by the single existing bot identity. Keep the game log
attributable per seat so history-service and eval-service see every seat's moves.
Leave every existing single-player caller behaving identically.

**Non-Goals.** A second DragnCards account. Per-seat websockets. Seat authority
enforcement (upstream has none; the orchestrator's `check_seat_scope` is where the
rule lives for us). Anything about credential caching or pooling.

## Decisions

### Decision 1: `player_n` becomes a parameter of prebuilt-deck loading, defaulting to `player1`

`GameSession.load_prebuilt_deck` builds a `RawAction(action_list=["LOAD_CARDS", deck_id],
player_n="player1")`. Marvel Champions hero decks declare their cards against
`playerNDeck` and `playerNNemesisSet`; DragnCards substitutes `N` from `$PLAYER_N`.
Fixing `$PLAYER_N` at `player1` therefore does not merely mislabel the load — it
puts every hero's cards in seat 1's groups.

The parameter threads through `SessionManager.load_prebuilt_deck` and the HTTP
endpoint as an optional field defaulting to `player1`.

*Alternative rejected — make `player_n` required.* It is the honest signature, but
`load_prebuilt_deck` is an MCP tool that the Marvel Champions skill already calls
during setup, and the orchestrator's seat guard cannot see an argument that is
absent. Making it required turns every existing call into an error at exactly the
moment no LLM provider is available to re-teach the skill. Defaulting keeps
single-player behaviour bit-identical and lets the skill adopt the argument on its
own schedule.

*Alternative rejected — infer the seat from the deck.* A deck's `loadGroupId` values
are templates (`playerNDeck`), not seats; there is nothing in the deck to infer
from. Scenario and modular decks legitimately load into `shared*` groups and want no
seat at all.

### Decision 2: the seat endpoint takes `player_id`, not `player_index`

The existing contract is wrong in both directions. Upstream `set_seat` uses
`player_i` as a map key:

```elixir
# game_ui_server.ex:328-338
def handle_call({:set_seat, _user_id, player_i, new_user_id}, _from, gameui) do
  ... GameUI.sit_down(gameui, player_i, new_user_id)
# game_ui.ex:71-75
def sit_down(gameui, player_n, user_id) do
  ... |> put_in(["playerInfo", player_n], player_info)
```

so `player_i` must be the string `"player2"`. Our request model types it `int` and
documents it as zero-based, which makes the correct value unrepresentable: against
the running service `"player2"` is a 422 and `2` writes a `playerInfo` key that
names no seat. Meanwhile `_auto_seat` passes the string, so the one internal caller
that works does so by contradicting the published contract.

The field becomes `player_id`, constrained to `player1`..`player4`. `player_index`
is dropped rather than deprecated: it never worked through the HTTP surface, the
endpoint is excluded from MCP (`route_maps` in `mcp/server.py`), and keeping a
broken alias alive would preserve the exact ambiguity being fixed. The type
annotations on `GameSession.set_seat` and `PhoenixRoom.set_seat` are corrected from
`int` to `str` to match what has always been sent.

### Decision 3: seating is verified by reading state back, not by awaiting a reply

`PhoenixRoom.set_seat` goes through `send_room_event`, which builds a `PhxMessage`
and writes it to the socket without registering a pending future. Nothing is ever
awaited, so a rejected or dropped `set_seat` is indistinguishable from a successful
one and the endpoint's 204 means only "we wrote bytes to a socket".

Seating is confirmed by re-reading room state and checking that the seat now holds
the expected user id, polling briefly because the write is asynchronous.

*Alternative rejected — await the channel reply.* Upstream's clause ends
`{:reply, :ok, socket}` rather than `{:reply, {:ok, _}, socket}`, so the reply shape
differs from the one `Channel.push` is written against, and the reply would in any
case only confirm the message was handled — not that the seat changed, since
`sit_down` swallows its own failure into `put_in(gameui["error"], true)`. Reading
the state answers the question actually being asked.

*Alternative rejected — trust the write.* That is today's behaviour and it is how
defect 3 stayed invisible.

### Decision 4: seats are claimed to match the player count

`playerInfo` needs an entry per seat in play, because the plugin dereferences it for
log attribution. The natural trigger is the player count: the orchestrator skill
already calls `set_player_count_action` to the roster size, and a room's player count
is precisely the set of seats that should be occupied.

So setting the player count to N claims seats `player1`..`playerN` for the service's
own DragnCards identity, skipping seats already held by someone else. Claiming is
best-effort: a seat that cannot be claimed is logged and the player-count change
still succeeds, because a missing log alias must never block setting up a game.

The identity to seat is read out of the room's existing `playerInfo` — the service
is already seated in one seat by `_auto_seat`, so its user id is in the state we
just fetched. Only if no seat is held does the service fall back to an HTTP profile
lookup. This keeps the change out of the session record and out of Valkey entirely:
no new persisted field, nothing new to restore, nothing new to migrate.

*Alternative rejected — claim all four seats at session creation.* A one-player game
would show three phantom occupants, and the count is not known at creation.

*Alternative rejected — claim a seat lazily, the first time an action names it.*
Actions are the hot path and this would add a state read and a conditional write to
every one of them, to fix something that is a property of the room's setup.

### Decision 5: a second DragnCards identity is deferred, and here is exactly what it would buy

This is the issue's own hypothesis, so it deserves a precise disposition rather than
a dismissal.

With one identity seated in several seats, `playerInfo` is complete and the log lines
exist, but every seat's alias is the same string. Observed in a two-player room, the
end-phase log currently reads:

```
dev_user draws 6 cards.          <- seat 1
                                 <- seat 2: nothing at all
```

Claiming seat 2 turns the blank into `dev_user draws 5 cards.` — present, ordered,
and attributable by position within the `$PLAYER_ORDER` loop, but not by name.

A distinct identity per seat would make it `capbot draws 5 cards.` The interesting
part is *how little* it would take: `set_seat` accepts an arbitrary `new_user_id` and
does nothing but `Users.get_user(user_id)` to read an alias. The extra users would
need to **exist**, not to authenticate — no second token, no second socket, no
second credential in our configuration. That is a much smaller change than the issue
imagines, and it is worth recording so nobody rebuilds it as an auth feature.

It is deferred because it is an attribution nicety with a real cost: registering
users against the DragnCards deployment is a side effect on shared infrastructure, it
needs configuration and secret handling for accounts that never log in, and the
per-seat naming that evaluation actually consumes already exists on the orchestrator
side as DRA-30 personas and display names. If per-name attribution inside the
DragnCards log is later wanted, the work is "create N users, seat them" and nothing
more.

One consequence to be aware of if that is ever revisited:
`get_player_n_by_user_id/2` uses `Enum.find`, so a user id occupying two seats
resolves to the lowest-numbered one. That decides which client receives a targeted
`gui_update`. It does not matter here — the Marvel Champions plugin definition
fetched from the running backend contains zero occurrences of `GUI_UPDATE`,
`pendingGuiUpdates`, `PROMPT` or `SELECT_CARDS`, so no targeted GUI update is ever
generated for this game — but it would matter for a plugin that used them.

## Risks / Trade-offs

**Upstream `set_seat` is unauthorized, and we are now using it more.** Any client in
the room can seat or eject any user id; `handle_call({:set_seat, _user_id, ...})`
discards the requester. Claiming seats does not create this exposure and cannot
close it — it is upstream behaviour in code we do not modify. It is bounded by the
room being reachable at all, which is the same boundary that already lets any joined
client replace the entire game state via `resolve_action_type`'s `"set_game"` branch.

**A seat claimed by the service looks occupied to a human.** Somebody joining the
room in a browser to watch or take over will find the seat taken by `dev_user`.
DragnCards' own `set_seat` lets them take it, and the claim is not re-asserted after
setup, so this is recoverable rather than sticky.

**Log aliases remain ambiguous between seats.** Accepted, and argued in Decision 5.
The alternative to ambiguity today is absence, which is worse for evaluation.

**The state read-back in Decision 3 is a poll, not a subscription.** It costs a short
bounded wait on a setup-time endpoint. Actions are untouched.

## Concurrency: already handled, deliberately not re-solved

Two seats acting at once in one room is the obvious hazard, since `execute_action`
is a non-atomic sequence — push, wait for a state change, request fresh state, scan
`game.messages` for an error — and a second action interleaved into it could have
its state update consumed by the first and its error attributed to the wrong caller.

This is already prevented. Every mutating route wraps its work in
`SessionManager.session_operation_lock(session_id)`, a Valkey `SET NX PX` lock, so
actions on one session serialize across replicas and not merely within one process.
`load_prebuilt_deck` and the player-count route take the same lock. The seat-claiming
in Decision 4 runs inside the player-count route's existing lock rather than taking a
second one.

No new locking is introduced. The finding is recorded here so the absence of new
concurrency machinery reads as a conclusion rather than an omission.

## Migration

None. No persisted shape changes, no Valkey key changes, no database. The only
breaking surface is `SetSeatRequest`, an HTTP-only endpoint that is excluded from
MCP and whose previous field could not express a working value.
