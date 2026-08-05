# Tasks

## 1. Seat vocabulary

- [x] 1.1 Add `services/game-service/src/game_service/logic/seats.py` with the seat id
      constants, a `normalise_seat_id` that accepts `player1`..`player4` and rejects
      everything else, and a `seat_occupants` reader that returns seat → user id from
      a room state, preferring `playerInfo` and falling back to `playerData`
- [x] 1.2 Add a `seats_to_claim` helper returning the vacant seats up to a player
      count, skipping every occupied seat whoever holds it
- [x] 1.3 Unit-test `seats.py` against both state shapes, a partially occupied room,
      a room where another user holds a seat, and rejection of bad seat ids

## 2. Prebuilt deck loading takes a seat (WebSocket payload)

- [x] 2.1 Give `GameSession.load_prebuilt_deck` a `player_n` parameter defaulting to
      `player1` and pass it into the `RawAction` instead of the hard-coded value
- [x] 2.2 Thread `player_n` through `SessionManager.load_prebuilt_deck`
- [x] 2.3 Unit-test that a non-default seat reaches the pushed `player_ui.playerN`
      and that omitting the argument still loads as `player1`

## 3. Prebuilt deck loading takes a seat (HTTP + MCP)

- [x] 3.1 Add `player_n` to `POST /games/{session_id}/load-prebuilt-deck`, validated
      against the seat ids, defaulting to `player1`
- [x] 3.2 Unit-test the endpoint for the default, an explicit seat, and a rejected
      seat id
- [x] 3.3 Confirm the derived MCP tool exposes `player_n` in its schema

## 4. Seat assignment speaks DragnCards' seat vocabulary (WebSocket payload)

- [x] 4.1 Correct `PhoenixRoom.set_seat` and `GameSession.set_seat` to take a seat id
      string, matching what has always been sent on the wire
- [x] 4.2 Add a verified claim on `GameSession` that pushes `set_seat` and then polls
      room state until the seat holds the expected user id, raising `SessionError` on
      timeout
- [x] 4.3 Unit-test the verified claim: success on first read, success after a delayed
      read, and failure when the seat never changes

## 5. Seat assignment speaks DragnCards' seat vocabulary (HTTP)

- [x] 5.1 Replace `SetSeatRequest.player_index` with `player_id` constrained to
      `player1`..`player4`
- [x] 5.2 Make `POST /games/{session_id}/seat` report a failed claim as an error
      instead of returning 204 unconditionally
- [x] 5.3 Unit-test the endpoint for a successful claim, a rejected seat id, an
      unknown session, and a claim that never takes

## 6. Seats are claimed to match the player count

- [x] 6.1 Add `SessionManager.claim_seats`, resolving the service's own user id by
      asking DragnCards rather than inferring it from whoever already holds a seat —
      a human may be sitting there — and claiming each vacant seat up to the player
      count without taking a second session lock
- [x] 6.2 Call it from the player-count route inside the existing session lock, after
      the count has been applied, logging and continuing when a seat cannot be claimed
- [x] 6.3 Unit-test: two-player count claims `player2`; a seat held by another user is
      left alone; a claim failure does not fail the player-count request

## 7. Documentation

- [x] 7.1 Add a "Seats are slots, not identities" section to
      `services/game-service/README.md` covering `player_n` as the only seat selector,
      the `Variable $PLAYER_N is undefined` failure mode, and the corrected seat
      endpoint contract
- [x] 7.2 Record the same rule in `services/game-service/AGENTS.md` so it is read
      before the next change to the action layer
- [x] 7.3 Correct the `README.md` session-creation wording that describes the service
      as being seated in "the first available player slot" to also describe claiming

## 8. Verification

- [x] 8.1 `./scripts/lint.sh --fix`
- [x] 8.2 `./scripts/test.sh unit` and compare against the recorded baseline
- [x] 8.3 `./scripts/test.sh integration game-service`, closing any room this change's
      own runs leave behind
- [x] 8.4 Drive the running stack end to end: create a session, set the count to 2,
      load a different hero into each seat through the prebuilt-deck endpoint, and
      confirm both seats' decks are populated and both seats' draw lines appear in
      the end-phase log
- [x] 8.5 `openspec validate --all` and compare against the recorded baseline
