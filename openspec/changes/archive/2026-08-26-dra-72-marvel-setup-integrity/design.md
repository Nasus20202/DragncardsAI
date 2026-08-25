# Design: Marvel setup integrity and render acknowledgement

## Context

The game-service Marvel adapter fetches the selected scenario and hero-deck documents and
sends them to `GET /new`. The engine response only says that the request was accepted. The
first useful world descriptor is obtained after the render WebSocket connects, but the
descriptor has no explicit setup id. It does contain the selected scenario's revealed
villain/main scheme and each player's selected identity card, which are sufficient
integrity witnesses without exposing engine internals above the platform seam.

The engine's render loop also waits for `GET /client_updated` before it reliably advances.
Frames with `ask_players=[]` are normal while a reveal resolves. Treating these frames as
absence of work and failing to acknowledge them leaves the engine waiting forever. At the
same time, an empty pending-seat list is not a legal decision and must never be converted
into a synthetic option.

## Goals

- Never return a Marvel session until its first ready world proves the requested scenario,
  ordered hero identities, and player count.
- Make a stale/default engine scene a loud, actionable creation failure.
- Make render acknowledgement reliable enough to advance setup, but bounded enough to
  degrade instead of hanging or retrying forever.
- Keep all engine hardening in repository-controlled Docker configuration or patch files.

## Decisions

### Decision 1: Validate setup witnesses at the driver boundary

`MarvelLcgPlatform.create_table` will parse the fetched scenario and hero documents into a
small private expectation containing the scenario villain and main-scheme card ids plus
the identity ids for each ordered hero deck. `connect` will acknowledge and process frames,
read the world, and then compare the expected witnesses with the world descriptor before it
returns. The check requires the selected number of players and one matching identity per
seat; it also requires the selected scenario's villain and main scheme to be present in the
scenario areas or their corresponding decks.

The expectation is derived only from document content already fetched through the live
catalog. It is not sent through the session model, and no raw world is logged in an error.
The error names the selected setup ids and the failed witness category, not card documents.

**Alternative rejected: trust `GET /new`.** Its success response confirms only request
parsing and does not prove which world the singleton engine presents.

**Alternative rejected: compare display names only.** Names are presentation data and are
less stable than the card identifiers already present in the engine descriptor.

### Decision 2: Acknowledge every useful frame with bounded retry

The platform will acknowledge each non-degraded frame after processing it. A per-seat async
lock prevents the background reader and a foreground wait from acknowledging the same render
out of order. Failed acknowledgements retry with a small bounded budget. Exhaustion marks the
seat as degraded, invokes the existing `on_state_unavailable` callback once, and causes an
operation that required the frame to raise `PlatformTransportError`.

The connect and post-submission wait loops will consume and acknowledge frames with an empty
`ask_players` list, then continue waiting for a frame that actually names the held seat.
They will not call `get_ask` as a substitute for turn authority and will not create options
when no seat is pending.

**Alternative rejected: treat acknowledgement as advisory.** That is the direct cause of
the empty-reveal hang.

**Alternative rejected: invent a no-op option for empty pending seats.** It would violate
the engine's option contract and could submit a move for a seat that is not being asked.

### Decision 3: Disable the startup-save fallback in the image

The repository-owned Marvel image will apply a second exact patch overlay to replace the
engine's hardcoded Rhino/Spider-Man fallback when a configured startup save cannot be
loaded with an explicit startup failure. The normal entrypoint continues to omit the
startup-save setting, but the image is safe even if a stale configuration supplies it.

## Risks and mitigations

- Some scenarios may not expose a villain or scheme immediately. The first ready frame is
  after engine setup, so the check uses both in-play and deck areas and reports a mismatch
  rather than guessing when a required witness is absent.
- A transient acknowledgement failure can make a session unavailable. This is preferable to
  returning or advancing a state the engine has not accepted; retry is bounded and the
  failure identifies render transport degradation.
- The vendored fork may change the exact fallback lines. Docker applies the patch with
  zero fuzz, so an unexpected upstream change fails the image build instead of silently
  shipping without the hardening.
