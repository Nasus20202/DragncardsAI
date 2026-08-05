# A history bundle you can re-import, and read

## Why

DRA-39 asks for four things from the history bundle: an "import as" that does not
409, a smaller file, a readable file, and a full/minimal mode pair. Three of them
turn out to be one problem, and one of them turns out not to be the problem it
looks like.

### The 409 is a missing control, not a missing capability

`POST /import` already takes a target: `game_id` when the caller supplies one,
otherwise the `game_id` in the bundle's own header. Against the running stack:

```
POST /import                          -> 409  "game '60f5d073-…' already has recorded history"
POST /import?game_id=dra39-probe-1    -> 200  {"game_id":"dra39-probe-1","source_game_id":"60f5d073-…",…}
```

So exporting a game and importing it back 409s for exactly one reason: nothing
ever passes a different target. The dashboard's import control posts the file and
no query string at all, so it always aims at the id already occupied by the game
the bundle came from. The fix is a control, not a new mechanism — plus one
genuinely missing affordance, a target the *server* mints, so that "import this as
a copy" needs no id from the caller and cannot collide.

What the 409 does hide is a second question the API never answered: an imported
game's payloads still name the game it came from. In a real 124-event export the
source `game_id` appears **4 273 times** inside `agent_move` payloads —
`arguments.session_id` (54), and the captured conversation's message text and
tool-call arguments (4 219). None of it is rewritten today and none of it should
be — see `design.md` — but until now nothing said so either, which is the
"silently" in "silently corrupt". This change makes the provenance explicit and
counts the references instead of pretending they are not there.

### The file is 94% repetition

A real recorded game measured at 31 332 926 bytes for 124 events. Where it goes:

| Subtree | Bytes across the game | Distinct values |
|---|---|---|
| `game_state.payload.state.game.cardById` | 8.11 MB | 25 of 50 |
| `game_state.payload.state.deltas` | 10.26 MB | growing prefix — 219 KB of content |
| `agent_move.payload.conversation_context` | 7.41 MB (7 432 messages) | 258 messages, 0.22 MB |
| `game.functions` + `automationActionLists` + `ruleById` + `ruleMap` + `layout` | 1.41 MB | **1** each |
| snapshots | 1.47 MB | ~245 KB each, near-identical to a `game_state` event |

`state.deltas` is DragnCards' append-only delta log: every `game_state` event
carries the whole list to date, so the 54th event re-ships the first 53 deltas.
Every agent move re-ships the entire conversation that preceded it. The plugin's
static definitions — its DragnLang functions, automation lists, rules and layout —
are byte-identical on all 50 states and both snapshots. This is not a game that
needs 31 MB; it is 1.6 MB of game shipped 20 times.

### "Human readable" and "small" are the same fix here, not opposites

A 450 KB minified line is not readable at any size. Pulling repeated values onto
their own lines and referencing them makes an `event` line a few hundred bytes you
can actually read — the whole 132-record spine of that game becomes 89 KB — and
makes the file 16.6× smaller at the same time. The two goals only diverge at the
margins (indentation, key spacing, naming each extracted value), and those margins
are cheap enough to spend: see the measured cost in `design.md`.

### The modes

"Full (with prompts) and minimal (game only)" is a content axis, not a size one,
but here it is both: eliding the captured LLM conversation takes the same game from
1 888 826 bytes to 957 821. The line has to be drawn precisely and recorded in the file, so
that a minimal bundle can never be mistaken for a full one whose prompts happened
to be empty.

## What Changes

- **Bundle format version 2.** A new `blob` record kind carries any repeated value
  once; `event` and `snapshot` payloads reference it as `{"$ref": "b7"}`. References
  are backward-only, so both export and import stay streaming. Version 1 bundles are
  still accepted on import — they are already explicitly versioned, so detection is
  a field read, not a guess.
- **`GET /games/{game_id}/export?mode=full|minimal`.** `full` is the default and is
  lossless. `minimal` elides exactly the LLM prompt material — `agent_move`'s
  `conversation_context` — and the header records both the mode and the list of
  elided payload fields.
- **`POST /import?as_new=true`** mints a fresh target id server-side. `game_id` and
  `as_new` together are a `400`. The `409` message and the import response both name
  the source game, and the response reports how many imported events still mention
  it.
- **Dashboard: an import dialog.** The import control opens a small form — import
  under the bundle's own id, under a new id the server mints, or under an id the
  user types — instead of firing a bare POST. The export control offers the two
  modes. The success notice reports the mode and, when the target differs from the
  source, how many events still name the source game.
- **A ref-expansion ceiling on import**, because backward references are a
  compression format and every compression format is a decompression bomb until
  someone bounds it. It reuses the existing `HISTORY_IMPORT_MAX_BYTES`, so there
  is no new setting to get wrong.
- **Restore stops calling an empty conversation a restored one.** A minimal
  bundle walks straight into an existing hole: `restore_session([])` succeeds, so
  a minimally imported game would report `agent_context_restored: true` with the
  agent remembering nothing. The game state still restores; the response now says
  the conversation was not rebuilt, and why.

## Impact

- Affected specs: `history-event-store`, `game-history-ui`
- Affected code:
  - `services/history-service/src/history_service/schemas/transfer.py`
  - `services/history-service/src/history_service/runtime/bundle_codec.py` (new)
  - `services/history-service/src/history_service/runtime/transfer.py`
  - `services/history-service/src/history_service/runtime/restore.py`
  - `services/history-service/src/history_service/api/routers/transfer.py`
  - `services/history-service/src/history_service/storage/repository.py`
  - `services/dashboard/features/history/components/history-transfer.tsx`
  - `services/dashboard/features/history/lib/history-api.ts`
  - `services/dashboard/features/shared/lib/types.ts`
- Not affected: `POST /import` and `GET /export` remain excluded from the MCP
  surface, so no MCP tool schema changes.
- Storage is untouched: no migration, no new column, no new table.
