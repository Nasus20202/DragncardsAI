# Judge a move in the context of its round, and make the scopes selectable

## Why

A user reported that move evaluation is inaccurate and that its scopes are
confusing:

> Currently each move is evaluated on it's own. This causes a valid moves like
> "exhaust + add tokens" to be analysed separately, leading to very low results.
> The move should be analysed in scope of the round and no the singular action.
>
> Please also make the move/round/whole game scopes easier to understand.
> Currently it's confusing - to evaluate a round, you have to select ID of a move
> in this round.
>
> Make sure to attach not only previous moves, but also the following ones.
>
> The goal is to make the evaluation more accurate.
>
> Please also adjust the UI to follow the guidelines.
>
> Evaluation of multiple actions can be done in parallel.

All five complaints reproduce.

### A move is graded as if it were a whole play

A Marvel Champions play is normally several MCP calls. Playing an ally and using
its ability is `move_card` (ally into play), `exhaust_card` (pay the ability
cost), `modify_tokens` (assign the damage). Each of those is a separate `agent`
event, so each becomes a separate `scope=move` target with its own verdict.

Nothing in the prompt tells the judge that a move can be one step of a larger
play, and the rubric asks four questions that a fragment cannot answer well:
`strategic_quality` ("was it a strong strategic choice toward winning?") and
`tempo_efficiency` ("no wasted tempo?") both read as low for `exhaust_card`
considered alone — exhausting a character accomplishes nothing by itself. The
reporter's "exhaust + add tokens" is exactly this: two calls that are one good
play, scored as two mediocre ones, twice.

### The context window is a fixed count that ignores the round

`EVAL_JUDGE_MOVE_CONTEXT_BEFORE` (8) and `EVAL_JUDGE_MOVE_CONTEXT_AFTER` (3),
introduced by DRA-7, bound a window of *the nearest N agent moves in the
timeline*, with no relation to a round. That has two consequences:

- The window silently crosses round boundaries. The 8 "preceding" moves of the
  first move of a round are the previous round's moves — a different turn, a
  different board, and not context for this decision.
- The window silently stops inside a round. With `AFTER=3`, a move at the start
  of a 15-move round is graded without seeing 11 of the moves that complete the
  play it belongs to. The following half exists but is too small to be the fix
  the reporter asked for.

### Selecting a round means selecting a move inside it

The Evaluate panel presents two orthogonal, independently-chosen groups: a
**Scope** radio (`Move` / `Round` / `Whole game (cascade)`) and a **Targets**
radio (`Selected event` / `Seq range` / `Whole game`). The scope decides what
kind of verdict is produced; the targets decide which sequences are selected.
Nine combinations exist, several are meaningless (`Move` + a range that contains
no agent move), and the only way to grade one round is `Scope: Round` +
`Targets: Selected event` — that is, click a move in the transcript so its `seq`
resolves to its containing round. The reporter's complaint is literal and
correct: to pick a round you pick a move.

The API already accepts `selection.rounds` — the UI has simply never used it,
because the dashboard has no list of the game's rounds to offer.

### Parallelism is bounded by a process-local dictionary

`EvaluationWorker` claims up to 64 pending targets per drain and runs them as
asyncio tasks, so evaluation *is* concurrent. But the bounds are
`self._global_sem` (8) and `self._game_sems: dict[str, asyncio.Semaphore]` at
`EVAL_PER_GAME_CONCURRENCY` = 2:

- Two at a time per game is close to serial for a whole-game cascade. The
  reporter's "can be done in parallel" is a request for it to actually be so.
- `_game_sems` is in-process state, which this repo's `AGENTS.md` forbids
  ("Services must NOT store any state in memory"). It also never evicts, so it
  grows by one semaphore per game for the process's lifetime, and with more than
  one replica the per-game cap is not a cap at all.

## What Changes

### 1. DRA-10 supersedes DRA-7's payload trimming (stated for the record)

DRA-7 did two separable things. This change **overrules the first and keeps the
second**, on the repo owner's explicit ruling that filing DRA-10 is itself the
statement that today's behaviour is wrong and that accuracy takes priority over
payload size:

| DRA-7 did | DRA-10 |
| --- | --- |
| (a) Trimmed the judge payload to a **narrow fixed-count neighbour window** (8 before / 3 after) | **Superseded.** The window becomes the move's whole round, in both directions. Prompts get bigger. That is the intended outcome, not a regression. |
| (b) **Skipped** evaluating actions that cannot be a wrong decision (card searches, session plumbing, pre-game setup) | **Kept unchanged.** Orthogonal to accuracy: it removes evaluations that were never meaningful. Widening (a) while dropping (b) would cost more for no accuracy gain. |
| (c) **Projected** the recorded state to the board the playing agent saw, hiding hidden information | **Kept unchanged.** This was an accuracy and correctness win, not merely a size win — before it, the judge saw ~20 KB of DragnCards' internal delta log and no board at all. |

No flag is added to preserve (a). A future reader should not have to work out
which of the two changes won: DRA-7's fixed-count window is gone, and the round
is the window.

`EVAL_JUDGE_MOVE_CONTEXT_BEFORE`/`_AFTER` survive **only as safety backstops**
against a pathological round, with defaults raised from 8/3 to 100/100 — the
same ceiling `EVAL_JUDGE_MAX_ROUND_MOVES` already uses for a round roll-up. They
are no longer the mechanism, and `_AFTER=0` still removes hindsight entirely for
an operator who wants that. The measured cost of the wider window is below.

### 2. A move's context is its round, in both directions

`judge/rounds.py` (new) resolves the round span containing a move and selects the
agent moves inside it. `assemble_move_input` uses it: the window is *every agent
move of the target's own round*, split into the moves before and the moves after
the one being graded, clipped only by the backstops. `MoveInput` carries the
round number and span so the prompt can name the round.

A move whose round cannot be detected — during setup, before any recorded state
carries a round number — falls back to the fixed-count window over the whole
timeline, so no move loses its context because boundary detection came up empty.

Non-strategic moves are **not** filtered out of the window. They are skipped as
*targets* (DRA-7 (b), kept), but as context they carry intent: "searched for
Med Team, then played Med Team" is a more legible sequence than "played Med
Team". Accuracy wins, and a one-line neighbour is cheap.

### 3. The rubric is told that a play is several calls

The window is necessary but not sufficient: DRA-7 already sent 3 following moves
and the reporter still saw the defect, because the prompt never said what to do
with them. The rubric gains an explicit instruction — grade the move as the step
it is within the play its round reveals, do not penalise a step for being
incomplete on its own, and do not charge the same play against every call that
makes it up — and the move prompt states which round the move belongs to and
labels the two halves as "earlier in this round" and "later in this round".

This is the part that actually fixes "exhaust + add tokens". A judge that can see
the round but is still asked "was this a strong strategic choice toward winning?"
about `exhaust_card` in isolation will still answer "no".

### 4. Round labels follow the DRA-9 convention, via DRA-14's conversion

DragnCards `roundNumber` counts *completed* rounds, so it reads 0 for the whole
first round of play. Every round label a user or a judge sees is `roundNumber + 1`
("Round 1" for `roundNumber` 0), the convention DRA-9 settled for the History
transcript.

DRA-14 landed this conversion in the eval-service while this change was in
progress: `detect_round_boundaries` now reports the round OF PLAY through
`assembly.round_of_play`, and `selection.rounds` takes that number rather than the
raw counter. This change therefore does **not** re-derive the convention. It uses
it: `round_label` formats an already-converted round of play, `MoveInput.round_number`
carries what the boundaries report, and the rounds endpoint returns that single
number as `round_number` — so there is no raw-versus-display pair for a client to
get wrong. An earlier draft of this change carried its own `display_round` helper;
it was removed on rebase rather than left to duplicate DRA-14's.

### 5. A rounds endpoint, and a scope selector that is one question

`GET /games/{game_id}/rounds` returns the rounds the eval-service itself detects
— raw `round_number`, display `label`, `from_seq`, `to_seq`, agent-move count,
and the players who acted. One source of truth for boundaries: the dashboard does
not re-derive them (it would drift from the service, particularly while DRA-14 is
fixing boundary detection), and a round listed by the endpoint is by construction
a round the service can grade.

The Evaluate panel collapses the Scope × Targets matrix into a **single "What to
evaluate" choice** with three options, each of which owns its own follow-up:

| Choice | Follow-up | Submitted as |
| --- | --- | --- |
| **Moves** | the selected transcript event, or a `seq` range | `scope: move` |
| **Rounds** | a checkbox list of the game's actual rounds, labelled "Round 3 · 12 moves · #63–#94" | `scope: round`, `selection.rounds` |
| **Whole game** | none | `scope: game`, `selection.whole_game` |

Selecting a round now means selecting a round. No transcript selection is
involved, and the meaningless combinations are gone because they can no longer be
expressed. The server keeps accepting a mid-round `seq` for a round-scope request
(existing clients, and the requirement that a round-scope target resolve from any
sequence inside it) — the UI simply no longer needs it.

### 6. The panel is rebuilt out of the dashboard's Hero UI field components

The panel currently hand-rolls native `<input type="radio">`, `<input
type="number">`, `<input type="checkbox">` and `<fieldset>` elements — against
`services/dashboard/AGENTS.md` ("Always use Hero UI components from
`@heroui/react` instead of native HTML elements"), and inconsistent with the
`JudgeConfigPanel` immediately below it in the same drawer, which is built from
the shared `features/shared/components/form-fields` wrappers. The rework uses
`RadioGroup`/`Radio` for the single scope question, `CheckboxGroup`/`Checkbox`
for the round picker, the shared `TextInputField` for the range bounds,
`ToggleInfoRow` for re-evaluate, and `Alert` for the error and confirmation
states. Scope is the only surface touched; nothing else in the dashboard is
restyled, and the evaluation error surface is left alone for DRA-18.

### 7. Concurrency is bounded by durable state, not a process-local dict

`Repository.claim_pending_targets` gains the caps: within the claiming
transaction it counts the `running` rows globally and per game, and claims at
most the remaining capacity — at most `EVAL_GLOBAL_CONCURRENCY` targets in flight
and at most `EVAL_PER_GAME_CONCURRENCY` per game. The worker's `_global_sem` and
`_game_sems` are deleted: the bound is now a property of the durable claim, so it
holds across restarts, is not a growing in-memory dictionary, and cannot be
bypassed by a second replica draining the same table.

`EVAL_PER_GAME_CONCURRENCY` rises from 2 to 4 so a round's moves actually grade
in parallel; `EVAL_GLOBAL_CONCURRENCY` stays at 8 as the provider-stampede guard.

A round/game roll-up whose children are still in flight is re-deferred to
`pending` (existing behaviour). Now that a drain claims only as many rows as
there is capacity for, an all-deferred cycle would spin: `drain_once` therefore
reports *progress*, not rows touched, so a cycle in which every claimed target
merely deferred makes the worker wait out its poll interval instead of hot-
looping on the database.

### 8. Verdicts from before this change are not comparable, and are not mixed in

Move verdicts recorded before this change were produced from a different prompt
— a cross-round fixed-count window and no multi-call-play instruction — so their
scores are not on the same scale as the new ones. `EVALUATOR_VERSION` is `eval-2`
(it is already recorded on every verdict and already folded into the verdict
idempotency key, so re-evaluating a target under `eval-2` produces a distinct
history event rather than being deduped against its `eval-1` verdict). DRA-14 had
already bumped it to `eval-2` for its own boundary correction; the version now
covers both changes, which is correct — a single label per regime, and both
changes shipped in the same regime.

The per-player scorecard averages **only the newest evaluator version present**
for a game and discloses how many older-version verdicts it excluded, rather
than silently averaging two scales together. Old verdicts stay on the timeline
where they are labelled by their own version; they just do not contribute to an
aggregate that would misrepresent them.

## Payload and latency impact

**No recorded game was reachable for this change.** DRA-7 measured its figures
against the games on the running stack; five agents are running concurrently here
and starting the Docker stack is prohibited for this change, so the numbers below
come from driving the REAL assembly and prompt code over a **synthetic** game
shaped like the recorded ones — 3 rounds of 24 agent moves, one raw DragnCards
`game_state` per round carrying the delta log and 120 card definitions that
dominate a real one (270 KB of recorded state in total). They are a measurement of
this code on synthetic input, not a measurement of production, and are not
presented as one.

| Move prompt, mean | DRA-7 window (8 before / 3 after, cross-round) | DRA-10 round-scoped (backstop 100) |
| --- | --- | --- |
| Characters | 5,553 | 9,080 |
| ≈ tokens (3.6 chars/token) | ~1,540 | ~2,520 |
| Change | — | **+63.5%** |

So a round-scoped move prompt costs roughly **1.6× today's**. Two things put that
in proportion:

- The extra cost is entirely the round's other moves, rendered as one compact line
  each. On this fixture the window grows from 11 neighbours to 23.
- It is still a small fraction of what the prompt cost before DRA-7's state
  projection, which this change keeps. 270 KB of recorded state reduces to a 9 KB
  prompt; DRA-7 measured the pre-projection move prompt at 13,750 tokens, and
  ~2,520 is well under a fifth of that.

Cost scales with round length, and a round is the bound: a move prompt never grows
with the length of the game, so a 40-move round costs more than a 24-move one but a
40-round game costs no more per move than a 3-round one.

Latency scales with input tokens (time-to-first-token plus prompt processing), so a
+64% input increase should cost a similar fraction of per-target latency. Against
that, `EVAL_PER_GAME_CONCURRENCY` 2 → 4 doubles the in-flight targets per game, so
a round or whole-game evaluation should still finish faster in wall-clock than it
does today despite each prompt being larger. Neither latency figure is measured;
both are inferences from token counts.

Cost stays bounded by mechanisms this change does not weaken:
`EVAL_MAX_TARGETS_PER_REQUEST` (200), `EVAL_JUDGE_MAX_STATE_CHARS`,
`EVAL_JUDGE_MAX_ROUND_MOVES`, the neighbour backstops at 100/100, and the
now-durable concurrency caps.

## Non-goals

- **Round-boundary detection.** DRA-14 corrected it (a round now ends at the
  event that closed it, and rounds are numbered as rounds of play) and landed
  first. This change consumes boundaries and does not fix them; edits to
  `judge/assembly.py` are kept narrow for that reason, and this branch was rebased
  onto DRA-14 so the round-of-play conversion is used rather than duplicated.
- **Error propagation and the evaluation error display**, owned by DRA-18. The
  panel's error surface is left as it is.
- **Re-theming the dashboard.** Only the evaluation scope/selection surface
  changes. Every other component keeps its current look.
- **Re-grading existing verdicts.** No migration re-runs old targets; `force`
  re-evaluation is the deliberate, user-initiated path.
- **A distributed (Valkey) concurrency lease.** The durable Postgres claim
  already bounds in-flight work per drainer without adding an infrastructure
  dependency to a service that has none.
- **Changing the four rubric criteria** or the verdict schema.

## Impact

- Affected specs: `agent-move-evaluation` (round-scoped move context supersedes
  the fixed-count window; round-aware grading instruction; round listing
  endpoint; durable concurrency bounds; evaluator-version comparability),
  `game-history-ui` (single-question scope selection with a real round picker;
  Hero UI components in the evaluate panel; version-aware scorecard).
- Affected code: `services/eval-service/src/eval_service/judge/rounds.py` (new),
  `judge/assembly.py`, `judge/prompt.py`, `runtime/rounds.py` (new),
  `runtime/evaluator.py`, `runtime/worker.py`, `storage/repository.py`,
  `schemas/api.py`, `api/routers/evaluations.py`, `api/deps.py`, `config.py`;
  `services/dashboard/features/history/components/evaluation-control.tsx`,
  `components/history-scorecard.tsx`, `lib/eval-api.ts`,
  `lib/history-rounds.ts`, `features/shared/lib/types.ts`.
- New API surface: `GET /games/{game_id}/rounds`.
- Configuration changes: `EVAL_JUDGE_MOVE_CONTEXT_BEFORE` 8 → 100 and `_AFTER`
  3 → 100 (backstops, not the mechanism), `EVAL_PER_GAME_CONCURRENCY` 2 → 4,
  `EVALUATOR_VERSION` `eval-1` → `eval-2`.
