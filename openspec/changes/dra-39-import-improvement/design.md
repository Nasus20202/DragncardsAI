# Design

Every number below was measured on a real recorded game exported from the running
stack's history-service (game `35128894-0cad-4b53-b195-d74b7428fe2c`, 124 events,
6 snapshots, 31 332 926 bytes), not estimated. The version 2 figures come from
running that bundle through the exporter's own `BlobWriter` and reading the
result back through the importer's own `BundleReader`, which reproduced all 124
payloads and all 6 snapshots with zero differences.

## 1. The 409, and what a new id does to the references inside the payload

### Where the 409 comes from

`Repository.import_game_history` opens the writing transaction, takes the per-game
advisory lock, and refuses if the target already has a single event row:

```python
if existing.scalar_one_or_none() is not None:
    raise GameHistoryExistsError(f"game {game_id!r} already has recorded history; …")
```

That is the *only* source of the 409. It collides on one thing: the target
`game_id`. Nothing else in the store is globally unique — `event_id` has no unique
constraint at all, and `idempotency_key` and `seq` are unique only *within* a
`game_id` — so the same bundle can be imported any number of times under different
ids without touching a constraint. Verified against the running service:

```
POST /import                        409
POST /import?game_id=dra39-probe-1  200  5 events, 0 snapshots
```

So the capability exists; the caller never uses it. The dashboard's
`importHistoryBundle(file)` sends no `game_id`, so the target defaults to the
bundle header's own id — which is, by construction, the id of the game the user
just exported and which therefore still exists.

### Which shape: caller-supplied id, server-generated id, or a duplicate flag?

All three were considered and the answer is two of them, for a reason that is about
who knows the id rather than about convenience.

- **Caller-supplied `game_id` (keep).** This is the only shape that can express
  "restore this bundle onto the id my other tooling already expects" — a
  cross-environment copy, or a re-import after a deliberate delete. It already
  exists and is already validated at the route boundary by the same pattern that
  validates a path `game_id`. Nothing about it is wrong.

- **Server-generated id (add, as `as_new=true`).** The common case — "I exported
  this and want a second copy to poke at" — has no id to supply. Making the user
  invent one is asking them to solve the service's uniqueness problem by hand, and
  a hand-invented id is exactly the one that collides next time. A `uuid4` target
  cannot collide and matches how every other game id in this system is minted.

- **Changing the *default* to a fresh id (rejected).** Turning today's loud 409
  into a silent copy would break the one case where the current default is right:
  re-importing a bundle after deleting the game, where landing on the original id
  is the whole point. A loud conflict that names the alternative is better than a
  silent surprise.

- **A `duplicate=true` / `overwrite=true` flag (rejected).** `overwrite` is a
  destructive operation wearing a query parameter, and the spec is explicit that
  import is not a way to modify an existing game's history — deletion is a separate
  endpoint on purpose. `duplicate` is just `as_new` with a name that suggests the
  new game is linked to the old one, which it is not.

`game_id` and `as_new` together are a `400`: they are two answers to one question,
and guessing which the caller meant is how you import a game to the wrong place.

### The references inside the payload — and why they are not rewritten

This is the part the 409 was hiding. Scanning the 31 MB export for its own
`game_id` finds it in three places, 4 273 times:

| Location | Occurrences | What it is |
|---|---|---|
| `agent_move.payload.conversation_context[].tool_calls[].function.arguments` | 2 530 | the session id the agent actually passed to a tool, inside the recorded tool call |
| `agent_move.payload.conversation_context[].content` | 1 689 | the id as it appeared in message text and tool results |
| `agent_move.payload.arguments.session_id` | 54 | the session id of the move as recorded |
| `header.game_id` | 1 | the bundle's own declaration |

There is a second family of identifiers that name the *original DragnCards room*
rather than the history game: `state.roomSlug` and `state.game.roomSlug`
(`unusual-journey-6419`) and `state.game.id` (`d32676cf-…`). These are not the
history `game_id` and were never equal to it, so they are unaffected by the choice
of import target — they were already "wrong" for any room but the one they came
from, and the restore path is built for that: it pushes `state.game` into whatever
room the restore target opens, and DragnCards owns the identity of that room.

**Decision: import does not rewrite payloads, and says so.** Three reasons:

1. `conversation_context` is evidence, not configuration. It is the verbatim record
   of what the model was shown and what it emitted, and it is the input the
   `evaluation` events judged. Rewriting an id inside a recorded assistant message
   would produce a transcript that no model ever emitted, and would silently
   invalidate every stored verdict that reasoned about it.
2. Blind substitution is unsafe at this scale. The only mechanism that could reach
   all 4 273 occurrences is string replacement across whole board states and free
   text; a 36-character UUID is not a safe token to search-and-replace inside 31 MB
   of someone else's JSON, and a bug there is undetectable.
3. Nothing dereferences them. `arguments.session_id` is recorded output — the
   argument the tool call carried — and no reader in this repository resolves it
   back to a live game-service session. The restore path addresses its target by
   the *route* `game_id`, never by anything inside a payload.

What changes is that the ambiguity stops being silent:

- The bundle header already carries the source `game_id`; the import response
  already echoes it as `source_game_id`. Both stay.
- The import response gains **`source_id_references`**: how many imported events
  contain the source `game_id` somewhere in their payload, counted while the
  bundle is read. When the target differs from the source and that count is
  non-zero, the dashboard says so in its success notice.

The count is cheap precisely because of the deduplication described next: repeated
content is scanned once as a blob rather than once per event.

## 2. Making it smaller: one generic rule instead of a list of fields

### What was actually duplicated

| Subtree | Bytes across the game | Distinct values | Nature of the repetition |
|---|---|---|---|
| `state.deltas` (per `game_state` event) | 10.26 MB | 54 deltas, 219 KB total | strictly a growing prefix: event *n* re-ships deltas 1…*n*−1 |
| `state.game.cardById` | 8.11 MB | 25 of 50 | half the events change no card at all |
| `agent_move.conversation_context` | 7.41 MB / 7 432 messages | 258 messages / 0.22 MB | every move re-ships the whole prior conversation |
| `state.game.functions` | 0.65 MB | **1** | plugin DragnLang definitions, identical everywhere |
| `state.game.automationActionLists` | 0.35 MB | **1** | ditto |
| `state.game.ruleById` / `ruleMap` / `layout` / `options` / `imageUrlPrefix` | 0.41 MB | **1** each | ditto |
| 6 snapshots | 1.47 MB | ~245 KB each | a snapshot's `game` largely repeats a `game_state` event's |

### The rejected approaches

- **Drop fields by name** (`deltas`, `sockets`, `spectators`, `cachedTimeout`,
  `privacyType`, `pluginAuthorId`, plugin statics). This is what "remove useless
  data" sounds like, and it is the wrong trade *once deduplication exists*. The
  restore path reads only `state.game` from a `game_state` payload, so `deltas`
  looks droppable — but the export is also the archival record that the evaluation
  pipeline and any future reader see, and every dropped field is a permanently
  lossy round trip in exchange for, after deduplication, **13 %** of the file
  (`deltas` costs 219 KB of a 1 888 826-byte bundle, the plugin statics 28 KB). Trading
  exactness for 13 % is a bad deal, and it is a deal that has to be re-made every
  time DragnCards adds a field. Nothing is dropped in `full` mode.
- **`Content-Encoding: gzip`.** `gzip -9` of the same file is **3 117 144 bytes** —
  more than 1.6× the size of the format below — and produces something no human can open,
  diff, or grep. It also cannot express modes. It remains available on top of the
  new format for anyone who wants it.
- **Delta-encoding each state against the previous one.** Smaller still, but it
  makes every line unreadable in isolation (you cannot see a board without
  replaying every board before it) and makes a single corrupt line poison the rest
  of the file. Deduplication keeps every record self-describing once its blobs are
  resolved.

### The rule

While serializing an `event.payload` or a `snapshot.snapshot`, walk it top-down.
For any `dict` or `list` whose canonical serialization is **≥ 256 bytes**:

- if the identical value has been emitted before, replace it with `{"$ref": "b7"}`;
- otherwise emit it as its own `blob` line first (recursively deduplicated), then
  replace it with a reference to that line.

One rule, no field names, no DragnCards knowledge. It catches every row of the
table above at once: the growing `deltas` list matches at *element* level (each
delta is ~4 KB), `conversation_context` at *message* level, `cardById` at both
whole-map and individual-card level, and the plugin statics as single whole
values shared by all 50 events and both snapshots.

The one thing the rule does **not** apply to is the payload itself. A record's
own `payload` (or a snapshot's own `snapshot`) is walked but never extracted,
however large it is. Extracting it would leave the record's line reading
`"payload": {"$ref": "b7"}` — which says nothing about what the record is — and
it does not even pay: the blob wrapper plus the reference cost more than the
inlined skeleton saves. Measured both ways on the game above, extracting roots
produces 1 893 904 bytes against 1 888 826, so the readable choice is also the
smaller one and there is no trade to make.

Measured on the 31 332 926-byte game:

| Variant | Size (bytes) | % of original |
|---|---|---|
| original (v1) | 31 332 926 | 100 % |
| gzip −9 of the original | 3 117 144 | 9.9 % |
| **v2, `mode=full`** | **1 888 826** | **6.0 %** |
| v2, `mode=minimal` | 957 821 | 3.1 % |

The 132 header/event/snapshot/footer records themselves come to **89 KB** — the
spine of a whole recorded game now fits in a text editor, and each `event` line
is a few hundred bytes carrying its action, its arguments, its digest and its
status, with references standing in for the board state it shares with its
neighbours.

Threshold choice: 256 bytes. 128 bytes is smaller still (1 311 920 bytes) but
pulls four-line fragments onto their own lines, so a reader chases a reference
for something they could have read in place; 512 bytes leaves `cardById` entries
inline and the file nearly doubles (3 664 497 bytes). 256 bytes is roughly "big
enough that you would have scrolled past it anyway".

### Format hazards this creates, and their guards

- **Reference bombs.** Backward references are compression, and a blob may
  reference earlier blobs, so `b2 = [b1, b1]`, `b3 = [b2, b2]`, … expands
  exponentially. Each blob's *expanded* size is therefore tracked as it is read
  (own bytes plus the expanded size of every blob it references) and a bundle
  whose expansion exceeds the configured import ceiling is refused with `413`
  before anything is materialized.
- **Cycles and forward references** are impossible by construction: a reference may
  only name a blob defined on an earlier line, and a reference to an unknown id is
  a `400` naming the line.
- **Unbounded nesting.** Resolving references means recursing over structure the
  file chose, and Python's stack gives out around a thousand frames — a
  `RecursionError`, which is a `500`, where a stated refusal is a `400`. Version 1
  never walked a payload at all; it handed it to the JSON encoder, whose C
  implementation tolerates far deeper input than this code does. Depth is
  therefore bounded at 200 while the expansion is priced, which is the first walk
  of every record and every blob. The bound is on the **reading** side only, and
  that is sufficient rather than lazy: nothing deeper can enter the store, so the
  export side — which walks only what the store already holds — has nothing to
  guard against.
- **`$ref` colliding with real data.** A payload could genuinely contain
  `{"$ref": "…"}`. Any object whose only key is `$ref` or `$literal` is written as
  `{"$literal": <the object>}` and unwrapped on read, which nests correctly and
  round-trips exactly. Tested with payloads that contain both.
- **Import memory.** Resolving backward references means the blob table is held
  while the bundle is read, so import is no longer O(one record) — it is O(distinct
  content), bounded by the existing `HISTORY_IMPORT_MAX_BYTES` ceiling (64 MiB) and
  in practice far below it, since the whole 31 MB game deduplicates to 1.89 MB.
  Export remains O(one record) plus the digest table.

## 3. What "human readable" came to mean, and what it cost

The format was already NDJSON with sorted keys, and the endpoint already called
itself human-readable. It was not, for one reason: a single line was 450 KB.

"Readable" here therefore means four concrete things.

1. **A record fits on a screen, and still says what it is.** Deduplication is
   what delivers the first half: a `game_state` event goes from ~450 KB to a few
   hundred bytes. Leaving the payload root inline delivers the second half — the
   line still carries its `action_args`, `action_path`, `plugin_name`,
   `state_digest` and `status`, and references only `state`:

   ```json
   {"actor": "game-service", …, "payload": {"action_args": {"layout_id": null,
    "num_players": 1, "type": "set_player_count"}, "action_path": "actions",
    "plugin_name": "marvel-champions", "state": {"$ref": "b90"},
    "state_digest": "b516c21f…", "status": "standard"}, "seq": 1}
   ```

   This is the same change that made the file small; the two goals do not
   conflict at all at this end.
2. **An extracted value says what it is.** A bare `{"$ref": "b412"}` is *less*
   readable than the value it replaced unless the reader can find out what `b412`
   is without decoding the file. Every `blob` record therefore carries
   `first_seen`, the dotted path where that value first occurred —
   `event[42].payload.state.game.cardById` — so `grep '"first_seen": "event\[42\]'`
   answers "what did event 42 actually carry".
3. **Stable, sorted, diffable.** Keys stay sorted; blob ids are assigned in
   first-encounter order, so the same input produces a byte-identical file and two
   exports of related games diff to what differs.
4. **Legible spacing.** `json.dumps` default separators (`", "`, `": "`) are kept
   rather than switching to compact ones.

Points 2 and 4 are where readable and small genuinely pull apart, and the cost is
measurable:

| | Size (bytes) | vs. smallest |
|---|---|---|
| compact separators, no `first_seen` | 1 711 740 | — |
| compact separators, `first_seen` | 1 772 238 | +3.5 % |
| **default separators, `first_seen` (chosen)** | **1 888 761** | **+10.3 %** |

10.3 % of a file that already shrank by 94 % is worth spending: it buys back the
94 % as something a person can actually read. The one thing not spent:
**pretty-printing is not offered.** Indenting would break the one-record-
per-line invariant that makes the format streamable, makes errors reportable by
line number, and makes it greppable — and it roughly triples the size. A reader
who wants an indented record can pipe one line through `jq`, which is exactly what
NDJSON is for.

## 4. The full/minimal boundary

**`full`** (default) — every stored event and every stored snapshot, every field
verbatim. Lossless: export → import → export is byte-identical.

**`minimal`** — the same records, with the LLM *prompt material* elided. Precisely
one thing falls on that side of the line: `agent_move.payload.conversation_context`,
the captured system prompt, tool schemas, prior turns and tool results that were
sent to the model. Everything else stays, including the agent's `reasoning`,
`intended_action` and `arguments`, every `user_prompt`, every `evaluation`, every
`game_state`, and every snapshot.

Two boundaries were rejected:

- **Dropping non-`game_state` events entirely** ("game only" read literally). Event
  `seq` must be strictly ascending and gap-free from 1 — the store's import
  validation requires it, and it is what lets a reader treat `seq` as a position.
  A bundle with holes would either be rejected by its own importer or force that
  invariant to be relaxed for everyone. It would also throw away what the agent
  *did*, which is the most interesting part of a recorded game and is not a prompt.
- **Dropping `user_prompt` events.** A user prompt is the human's input to the
  game, not model prompt material, and the whole game's worth of them is 1.4 KB.

### Recording the mode so a minimal bundle cannot pass as a full one

The header carries `mode` and `omitted_payload_fields`, e.g.

```json
{"kind": "header", … , "mode": "minimal",
 "omitted_payload_fields": ["agent_move.conversation_context"]}
```

`full` writes `"mode": "full"` and `"omitted_payload_fields": []`. A version 1
bundle has neither and is read as `full`, which is what it is. Import validates
that `omitted_payload_fields` is empty when the mode is `full`, echoes the mode in
its response, and the dashboard's success notice names it.

Elision is by **absence, not emptiness**: a minimal bundle's `agent_move` payloads
have no `conversation_context` key at all, never `[]`. That distinction is what
stops a minimal import from looking like a full recording whose conversations were
empty, and it is asserted directly in the round-trip tests.

### The restore path had to be fixed for this, not just relied on

Downstream, a minimal import lands on a real hazard, and the format alone does not
solve it. `restore._extract_conversation_context` returns `[]` for an absent
field, and `restore_session(conversation_context=[])` **succeeds**: the
orchestrator creates a session, and the restore reports
`agent_context_restored: true` with a note of `null`. A minimally imported game
would therefore restore to "the agent is back at that moment" while the agent had
no memory of the game at all — the worst kind of wrong answer, because it is a
confident one. `schemas/envelope.py` names this failure mode already, and
`get_latest_agent_event_at_or_before` mitigates the part of it that is about event
*types* by excluding `AGENT_EVENT_TYPES_WITHOUT_CONTEXT` in the query.

So `_restore_agent_context` now treats an empty conversation the same way it
already treats a missing agent event: the game state restores, and the response
says `agent_context_restored: false` with a reason that names the `minimal` export
as a cause. This is not a special case for imports — it closes the general hole,
an event type that normally carries a conversation appearing in a recording that
does not.

Rejected alternative: refusing to restore a minimally imported game at all. The
game-state layer is the restore and the agent layer is an enhancement to it — the
spec already says so, and already reports "restored, without the agent
conversation, because …" for the in-place `404` case. Refusing would make a
`minimal` bundle unusable for the thing it is for, which is looking at a game.

`mode` describes the *export operation*, not a permanent property of a game. A
minimally-imported game genuinely holds no captured conversation, so re-exporting
it in `full` mode honestly reports `full` with no `conversation_context` present —
"this recording has no prompts", which is true, rather than "the prompts were
empty", which would be a lie.

## 5. Backward compatibility

**Decision: import accepts format versions 1 and 2; export always writes 2.**

Version 1 needs no sniffing. Its header already carries an explicit
`format_version: 1`, and `parse_header` already reads it — the "unversioned legacy
payload" problem does not exist here, because the first release of this format was
versioned. A version 1 bundle is recognised by that field, read with no blob table
(a `blob` record in a version 1 bundle is a `400`), and treated as `mode: "full"`
with no omitted fields. Every version 1 bundle a user has on disk still imports,
and the round-trip test suite keeps a checked-in version 1 fixture to prove it.

The break that *is* accepted: a version 2 bundle will not import into a
history-service built before this change. That is loud and specific — the existing
`parse_header` answers `unsupported bundle format_version 2 (this service reads
version 1)` — and there is no way to avoid it short of never changing the format.
Both directions of the mixed-version matrix are therefore either supported or
diagnosed, and neither is silent.

Version 3 is not anticipated by this change; the mechanism for it is the same field.

## 6. API surface

```
GET  /games/{game_id}/export?mode=full|minimal       (default full)
POST /import?game_id=<id>                            explicit target      (unchanged)
POST /import?as_new=true                             server-minted uuid4  (new)
POST /import                                         target = header game_id (unchanged)
POST /import?game_id=<id>&as_new=true                400
```

`ImportResponse` gains `mode` (from the bundle header) and `source_id_references`
(count of imported events whose payload mentions the source `game_id`; `0` when
the target and source are the same id, because then they are not stale).

Both routes stay excluded from the MCP surface for the reasons already recorded
there — export would buffer a whole game into a model's context, and import is a
write into the ordered store.

## 7. The one back-pointer this change does not fix, and why

There is exactly one place where a restored game can reach back to the game it
came from, and it is not in this repository's services. It is in vendored
DragnCards, and it predates this change.

A restore pushes the recorded `state.game` document into the target room verbatim.
That document carries the **original** room's `id` and `roomSlug`
(`external/dragncards/backend/lib/dragncards_game/game.ex:86-88`). DragnCards'
`save_replay_to_db` then looks a replay row up by `game["id"]`
(`game.ex:201-213`), so a restored room that auto-saves on its GenServer timeout
writes into the *original* game's replay row. `game_ui.ex:1097-1105` and
`RESET_GAME.ex:38` read the same stale slug.

**Decision: documented, not fixed, in this change.** Three reasons:

1. It is not caused by importing. Every restore has always pushed the original
   `id` and `roomSlug` into whatever room it opens, whether the history was
   imported, copied, or the game's own. An import under a new id changes nothing
   about it: the ids in `state.game` were never the history `game_id` and were
   already "wrong" for any room but the one they came from.
2. Fixing it means editing the recorded state on the way out — rewriting `id` and
   `roomSlug` inside `state.game` before `set_game` — which is a change to the
   restore path's contract with DragnCards, affecting every restore in the
   product. That deserves its own change, its own DragnCards-side verification,
   and its own answer to "what should a restored room's replay row be?", which is
   a product question this change has no standing to settle.
3. It cannot be triggered by anything this change adds. Import writes to the
   history store only; nothing about `as_new`, the modes, or the format reaches
   DragnCards.

What this change does do is stop pretending the id inside a payload is
meaningless: `source_id_references` counts them, and the import response and the
dashboard notice both name them. The DragnCards-side rewrite is the follow-up
that count makes visible.
