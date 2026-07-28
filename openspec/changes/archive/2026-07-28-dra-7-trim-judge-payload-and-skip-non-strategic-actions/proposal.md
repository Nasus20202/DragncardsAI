# Trim the judge payload and stop evaluating non-strategic actions

## Why

A user reported: "During evaluation we currently try to send too much data, we
should trim it reasonably (maybe send only neighboring actions, not the whole
history?). Also we should [not] waste time on evaluating actions that are not
game / strategy specific. For instance searching for cards is something that
cannot be a wrong decision (taking it into a hand can be though). Propose
something."

Both halves reproduce, and the first one is worse than "too much data".

### Measured, on the real recorded games in this stack

The largest recorded game (122 events) is **29.8 MB** of history — a mean of
245 KB per event. Every `game-service` `game_state` event carries the RAW
DragnCards room state, 64 KB at setup rising to **470 KB** by round 2. Of that
470 KB:

| Section | Bytes | What it is |
| --- | --- | --- |
| `deltas` | 224,807 | DragnCards' internal undo/replay log |
| `game.cardById` | 165,446 | Both faces of every card definition, incl. artwork geometry |
| `game.groupById` | 22,870 | Every zone's stack ids |
| `game.playerData` | 14,764 | Mostly per-seat UI layout |
| `game.functions` + `automationActionLists` + `ruleById` + `layout` | 27,485 | Plugin configuration |
| everything a judge actually needs | ~2,500 | round, phase, hit points, board |

A move prompt embedded **two** of these states, each clipped to
`EVAL_JUDGE_MAX_STATE_CHARS` (20,000) by a character slice of the canonical
(sorted-key) JSON. `deltas` sorts before `game`. So the clip never reached the
board: measured on the recorded game, the prior-state block was
`cachedTimeout`, `createdAt`, `createdBy`, and then ~19,900 characters of delta
log cut mid-object, followed by `...[truncated 434002 chars of prior state]`.

**Measured cost of that: 13,750 mean prompt tokens per move evaluation
(40,756 chars), across 97 real agent moves — spent showing the judge no board at
all.** Round roll-ups were worse in the other direction: a round's closing seq is
its LAST seq, which is usually an agent move and therefore carries no state, so
round prompts came out at 1,505 mean tokens *with no board*, and game roll-ups at
268 tokens — the rubric and nothing else.

Meanwhile 31 of those 97 moves were actions no judge can grade:
`search_prebuilt_sets_marvel_champions` (14), `load_prebuilt_deck` (12),
`set_player_count_action` (3), `load_cards` (1), `unload_cards` (1). Each one
burned a full judge call to score a card search on `rules_legality`,
`strategic_quality`, `tempo_efficiency` and `threat_resource`.

## What Changes

### 1. Project the recorded state instead of clipping it

A new `judge/state_view.py` projects a raw DragnCards state down to the same
`SimplifiedGameState` shape `game-service` already serves the **playing agent**:
round number, mode, step id and its description, per-seat hit points and hand
size, and per-zone card lists (instance id, name, type, stage, traits, live
tokens, exhausted, side, stack size). The judge therefore sees the same view of
the table the agent saw when it decided, which is the right basis for grading that
decision.

Face-down cards and cards showing a generic `player`/`encounter` back collapse to
a `HIDDEN` entry with a count. That is a size win (60+ deck cards stop being
serialised) *and* a correctness win: the rubric tells the judge not to assume
hidden information, and until now deck contents were at least eligible to leak in.

`EVAL_JUDGE_MAX_STATE_CHARS` stays as a **backstop**, not the mechanism. A state
shape the projection does not recognise — an already-simplified state, a test
fixture, a future shape — is serialised as recorded and clipped exactly as before,
so nothing is silently emptied.

Round and game roll-ups now fall back to the nearest recorded state at-or-before
their closing seq, so a roll-up is never graded with no board.

### 2. A configurable neighbouring-action window, not the whole history

`EVAL_JUDGE_MOVE_CONTEXT_BEFORE` (default 8) and
`EVAL_JUDGE_MOVE_CONTEXT_AFTER` (default 3) bound a window of the agent's own
moves included with a move prompt, each rendered as seq + action + arguments +
reasoning (reasoning clipped at `EVAL_JUDGE_MOVE_CONTEXT_REASONING_CHARS`).

**Why a window and not the whole history.** The prompt already carries the
correlated prior and resulting board, which summarise everything that happened
before, so replaying the full move list would add cost without adding signal —
that is the reporter's own instinct and it holds. **Why not zero, either.** What a
board cannot show is that one tool call is a fragment of a larger play: a Marvel
Champions play is typically 2-4 MCP calls (`move_card` the card into play,
`modify_tokens` for damage, `exhaust_card` the character) and a whole player turn
runs ~6-10. Judging `exhaust_card` with no neighbours invites a confidently wrong
verdict, which is worse than a slow one.

The defaults therefore cover a typical player turn's worth of preceding calls plus
just enough following calls to see whether a play completed. Measured on real
games the entire window costs ~600 prompt tokens — 4% of what the old delta-log
blocks cost. The following half is labelled in the prompt as completion context,
explicitly not an outcome to grade, and `EVAL_JUDGE_MOVE_CONTEXT_AFTER=0` removes
hindsight entirely.

Alternatives considered and rejected: **whole history** (what the reporter
suspected we were doing — we were not, and it is the wrong direction: at 56 moves
a game it would be pure cost); **a round-bounded window** (a round boundary is not
where a play begins or ends, so it both over- and under-includes); **a
token-budgeted window** (a second bound to tune, with no better answer than "the
current turn" once the board is projected).

### 3. A taxonomy of non-strategic actions, skipped visibly

`judge/actions.py` classifies a recorded `intended_action` (the MCP tool the agent
called). The dividing line is deliberately **not** whether the tool reads or
writes, but **whether the action commits game state in a way a player could get
wrong** — the reporter's criterion exactly: searching for a card cannot be a wrong
decision, taking one into hand can be.

**Non-strategic (skipped), 16 actions in three categories:**

| Category | Actions | Why |
| --- | --- | --- |
| Read-only | `get_game_state`, `get_session_actions`, `list_actions`, `list_card_providers`, `list_games`, `lookup_session_by_slug`, `search_cards_marvel_champions`, `search_prebuilt_sets_marvel_champions` | Return information and change nothing on the table. No decision exists to grade. |
| Session plumbing | `attach_game`, `create_game`, `delete_game` | Room lifecycle, outside the game entirely. |
| Pre-game setup | `load_cards`, `load_prebuilt_deck`, `multiple_double_sided_villains`, `set_player_count_action`, `unload_cards` | Establish the starting position rather than play from it. |

**Strategic (evaluated), everything else:** `deal_encounter`, `discard_minion`,
`discard_side_scheme`, `draw_boost`, `draw_card`, `exhaust_card`, `flip_card`,
`modify_tokens`, `move_card`, `mulligan_draw_hand`, `next_step`,
`player_end_phase`, `prev_step`, `raw_action`, `ready_card`, `set_card_property`,
`shadows_of_the_past`, `shuffle_into_deck`, `villain_encounter_phase`,
`villain_end_phase`, `zero_tokens` — plus **anything the taxonomy does not
recognise**, including a new tool, a tool from another MCP server, or a legacy
action name.

The asymmetry is intentional. Wrongly skipping a strategic action degrades
evaluation quality in a way nobody will ever notice; wrongly evaluating a trivial
one costs one judge call. So where there is doubt, we evaluate.

**The borderline calls, stated:**

- `draw_card` — draws in Marvel Champions are forced and the card is random, so it
  looks mechanical. It is nevertheless *the* example the reporter gave on the
  strategic side ("taking it into a hand can be" wrong), and *when* and *how many*
  you draw is a rules matter. Evaluated.
- `ready_card`, `zero_tokens` — bookkeeping the refresh phase normally performs,
  but readying the wrong card is a rules violation. Evaluated.
- `next_step`, `prev_step`, `player_end_phase`, `villain_encounter_phase`,
  `villain_end_phase` — largely forced sequencing, and 23 of 97 recorded moves are
  `next_step`, so keeping them costs the most of any decision here. But ending the
  player phase with actions unspent is a real, gradeable tempo error, and
  `prev_step` is itself a correction signal. Evaluated. This is the first place a
  future *measured* tightening should look.
- `deal_encounter`, `draw_boost` — rules-mandated with random content, but dealing
  to the wrong player or in the wrong phase is a real error. Evaluated.
- `mulligan_draw_hand` — deterministic ("draw up to hand size, never discards"),
  yet it stands where the opening-hand decision belongs. Evaluated.
- `set_card_property` — the generic escape hatch; can flip hero/alter-ego, which is
  one of the biggest decisions in the game. Evaluated.
- `load_prebuilt_deck` / `load_cards` — **the most debatable skip.** Deck choice is
  arguably the most strategic decision in a deckbuilder. Skipped anyway because
  (i) it is a construction decision, not a play, and none of the four rubric
  criteria apply to it, and (ii) in this system the deck comes from the user's
  request, not from in-game strategy. This is exactly why the list is
  configurable: `EVAL_NON_STRATEGIC_ACTIONS` moves any entry back into evaluation
  with one setting.

**Skipped means skipped, never passed.** A non-strategic move is recorded through
the existing `Repository.mark_skipped` channel — the same one a judge failure uses
— with the reason `non-strategic action 'search_cards_marvel_champions':
read-only query; commits no game state, so it cannot be a wrong play`. The target
row exists, reaches terminal status `skipped`, and appears in the request-status
aggregate and the dashboard queue as skipped with its reason. No verdict is
written. `EVAL_SKIP_NON_STRATEGIC_MOVES=false` grades everything.

Round roll-ups leave non-strategic moves out of their listed moves (the same
taxonomy) and state how many were omitted, so a round score is not dragged down by
a card search. A round whose every move was skipped still produces a roll-up: the
skip is a move-scope judgement.

## Results

All numbers below are **measured** by running the real prompt-assembly code
against the three recorded games in this stack that contain agent moves (97 agent
moves, 5 detected rounds, 3 games), tokenised with `tiktoken`/`o200k_base`.

| | Before | After | Change |
| --- | --- | --- | --- |
| Move prompt, mean tokens | 13,750 | 3,067 | **−77.7%** |
| Move prompt, mean chars | 40,756 | 9,059 | −77.8% |
| Move prompts issued | 97 | 66 | **−32.0%** (31 skipped) |
| Round prompt, mean tokens | 1,505 | 2,218 | +47.4% (gains a board) |
| Game prompt, mean tokens | 268 | 1,325 | +394% (gains a final board) |
| **Total prompt tokens, all 105 targets** | **1,342,068** | **217,510** | **−83.8%** |
| Move assembly + render, mean wall-clock | 7.3 ms | 0.5 ms | −93% |

The round and game increases are deliberate: those prompts previously contained no
board at all. They cost 8.7k tokens of the 1.12M saved.

**Not measured:** end-to-end judge latency and cost. No `eval-judge` key is
configured on this stack (`GET /ready` reports `judge_configured: false`, and the
gateway container exposes no `EVAL_JUDGE_*_API_KEY`), so the judge cannot be
driven end-to-end here. Wall-clock per evaluation is dominated by the provider's
time-to-first-token plus prompt processing, both of which scale with input tokens;
an 83.8% input reduction is expected to cut it substantially, but that is a
projection from the token counts, not a measurement, and it is not claimed as one.

## Capabilities

### New Capabilities

<!-- None -->

### Modified Capabilities

- `agent-move-evaluation` — bounded judge input becomes a projection plus a
  configurable neighbouring-action window; non-strategic actions are skipped with
  a recorded reason.
