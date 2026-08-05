# Two-player play: seats are slots, not identities

## Why

DRA-44 says *"Currently game service only works as `dev_user`. We might have to add
option to use multiple users, so that multi-user game are possible."* The premise
is wrong, and proving it wrong is most of the value of this change.

DragnCards does not model a seat as an authenticated user. A room's seats are the
keys `player1`..`player4` of one in-memory map inside a single `GameUIServer`
GenServer, and the seat an action acts as is taken **verbatim from the client's own
message payload**:

```elixir
# external/dragncards/backend/lib/dragncards_game/ui/game_ui.ex:772-773
game_new = game_old
  |> put_in(["playerUi"], options["player_ui"])
```

`$PLAYER_N` — the variable every piece of Marvel Champions automation branches on —
resolves to exactly that client-supplied `game["playerUi"]["playerN"]`. The socket's
authenticated `user_id` is used only to look up the user's language preference, to
attribute a saved replay, and to decide which client receives a targeted `gui_update`
push. It is never compared against the seat being acted as. The helper that would
perform that comparison, `GameUIServer.is_player/2`, exists and has zero call sites.

So one credential on one websocket can already drive every seat, and this was
confirmed against the running stack rather than inferred. Through a **single**
game-service session authenticated as the one `dev_user`, two different hero decks
were loaded into two different seats:

```
player1Deck 40   player1NemesisSet 5   player1Play1 1
player2Deck 40   player2NemesisSet 5   player2Play1 1
numPlayers 2
```

A second DragnCards account buys nothing for *acting*. What actually blocks
two-player play is three defects on our side of the wire.

**1. The only prebuilt-deck path is nailed to seat 1.** `GameSession.load_prebuilt_deck`
hard-codes `player_n="player1"`. Hero prebuilt decks load into the templated groups
`playerNDeck` and `playerNNemesisSet`, which DragnCards substitutes from `$PLAYER_N`.
With the seat fixed at `player1`, `POST /games/{id}/load-prebuilt-deck` and its MCP
tool can only ever fill seat 1's deck. This is the concrete thing behind "only works
as `dev_user`", and it is a one-field omission rather than a missing identity system.

**2. The seat endpoint cannot name a seat.** `SetSeatRequest.player_index` is typed
`int` and documented "Zero-based player seat index", but DragnCards' `set_seat` uses
`player_i` as a **string key** into the seat map. Against the running service,
`{"player_index": "player2"}` is rejected with HTTP 422 and `{"player_index": 2}`
returns HTTP 204 while changing nothing — the 204 is unconditional because
`PhoenixRoom.send_room_event` is fire-and-forget and never reads a reply. Internally
`SessionManager._auto_seat` calls the same function with the string `"player1"`, so
the two callers of one function disagree about its value space and only the
undocumented one works.

**3. Only one seat is ever registered, and that silently truncates the game log.**
`_auto_seat` takes the first vacant seat and returns; its "user already seated"
guard makes a second call a no-op. Seats 2-4 therefore keep `playerInfo[playerN] =
nil`. That is not cosmetic. The Marvel Champions `playerEndPhase` action list logs
each player's draw as `["DRAW_HAND", "$PLAYER", "$GAME.playerInfo.$PLAYER.alias"]`,
and `DRAW_HAND` guards the log line with `COND [DEFINED $CONTROLLER]`. With a null
alias the line is not written at all. Observed on the running stack in a two-player
room, the end-phase log contains `dev_user draws 6 cards.` for seat 1 and **no draw
line whatsoever** for seat 2. history-service records that log and eval-service
judges from it, so a whole seat's draws are invisible to evaluation. Errors raised
by seat 2 likewise read `[player2/player2]` instead of naming anyone.

## What Changes

- **`load_prebuilt_deck` accepts a seat.** The session method, the HTTP endpoint and
  the derived MCP tool take `player_n`, defaulting to `player1` so every existing
  caller is unaffected. This is what makes a two-hero game loadable.
- **The seat endpoint speaks DragnCards' seat vocabulary.** `POST /games/{id}/seat`
  takes `player_id` as `player1`..`player4`. It verifies the seat actually took by
  re-reading room state instead of returning 204 unconditionally, and reports a
  failure to seat as an error rather than as success.
- **Seats are claimed to match the player count.** When the player count is set to
  N, the service claims seats `player1`..`playerN` for its own DragnCards identity,
  so `playerInfo` is complete and the per-seat log lines the history and evaluation
  pipelines depend on are actually emitted.
- **The seat model is written down.** `services/game-service/README.md` and
  `AGENTS.md` gain a short section stating that a DragnCards seat is a slot, not an
  identity, that `player_n` on an action is the only thing that selects a seat, and
  that omitting it from an action that needs it fails with
  `Variable $PLAYER_N is undefined`.

## Non-goals

- **A second DragnCards credential, and any `BOT_EMAIL_2`-shaped configuration.**
  Nothing in the play path needs one. The single thing a distinct identity would buy
  is a distinct `alias` per seat in the game log; that is an attribution nicety,
  and DRA-30 already gives each seat a display name and persona on the orchestrator
  side where evaluation reads them. Deferring it is argued in `design.md`.
- **One websocket per seat.** It follows only from a second credential, and would
  multiply the reconnect, heartbeat and state-waiting surface for no gain.
- **Any change to the orchestrator's seat guard.** `check_seat_scope` already refuses
  a seat that names another seat's cards, and it is the right place for that rule.
  This change gives game-service the ability to *serve* a seat correctly; it does not
  touch who is allowed to ask.
- **Enforcing seat authority against DragnCards.** Upstream does not check it and we
  do not modify upstream. Authority stays where DRA-19/DRA-30 put it.
- **Connection pooling and credential caching.** DRA-36's territory.

## Impact

- Affected specs: `game-service`, `dragncards`
- Affected code: `services/game-service/src/game_service/logic/seats.py` (new),
  `logic/session.py`, `logic/session_manager.py`, `logic/room.py`,
  `api/models.py`, `api/routers/load_prebuilt_deck.py`, `api/routers/game_room.py`
- Affected docs: `services/game-service/README.md`, `services/game-service/AGENTS.md`
