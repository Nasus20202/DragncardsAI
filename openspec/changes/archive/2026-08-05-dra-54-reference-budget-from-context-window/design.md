# Design: what should stop a reference selection, and when

## The question

The owner asked for no limit. This document answers plainly: **one bound remains,
it is the model's context window, and every other bound is removed.** The rest of
this file is the argument for why that is the honest answer rather than a
softened refusal of the request.

## 1. The old bounds were placeholders, not physics

DRA-41 set two numbers this morning. Re-reading its own reasoning:

> Eight is above any plausible manual selection and far below the 21 files of the
> rules skill.

> 60,000 admits the largest single reference (`resources/errata.md`, 38,515 chars)
> plus a second substantial file such as `resources/timing.md` (15,344) — the
> realistic shape of "the judge needs the errata and the timing rules" — while
> refusing a whole-corpus selection outright.

Both are justified against an *imagined use*, not against a capacity. "Refusing a
whole-corpus selection outright" is stated as a goal in itself. DRA-54 is the
owner saying the whole corpus is exactly what they want, and nothing in DRA-41's
argument says they cannot have it. So the first thing to establish is whether they
can.

### Measured: the corpus, at this commit

Character counts are measured from `skills/` on disk. Token figures are
**projections at ~4 characters per token**, the convention DRA-41 established;
`EVAL_JUDGE_OPENROUTER_API_KEY` is unset, `judge_configured` is `false`, every
provider reports `available=false`, and no tokenizer for any judge model is
installed in `services/eval-service/.venv`. No prompt was sent and no token count
was measured.

| | chars | projected tokens |
| --- | --- | --- |
| all 28 reference files | 313,317 | ~78k |
| the 21 `marvel-champions-rules-reference` files | 256,568 | ~64k |
| all five `SKILL.md` | 91,355 | ~23k |
| the old budget | 60,000 | ~15k |
| a 128,000-token window | ~512,000 | 128k |

The old 60,000-character budget is **12% of a 128k window**. The judge's entire
non-reference prompt, once bounded (§4), is another ~216,000 characters. So the
old budget left roughly 236,000 characters of window unused on every single
evaluation. That is the finding: the bound was not protecting anything.

## 2. But a bound must remain, and this is the part the owner did not ask for

An over-window prompt does not degrade gracefully. It is a provider error. DRA-33,
merged today, is the evidence on the agent side: at threshold 0.8 the real request
reached 116,250 tokens, and 132,551 with four skills inlined, against a
128,000-token window. The judge is the same physics with a longer inlined body and
no compaction at all — there is no tool loop to fetch on demand (DRA-41 §1
established this: `_build_payload` sends no `tools` key, `parse_verdict` demands
exactly one JSON object, nothing reads `tool_calls`), so **everything selected is
in the prompt, always.**

Removing the bound outright therefore trades:

- **today** — one 400 at request time, before any target is enqueued, naming what
  was too big; for
- **after** — a request that is accepted, expands to a batch of up to
  `EVAL_MAX_TARGETS_PER_REQUEST` targets, and then fails *per target* inside the
  worker with a provider error whose text is written by the gateway. The user
  waits for the batch to fail to learn the selection was impossible, and pays for
  the retries on the way (`EVAL_MAX_ATTEMPTS`).

That is worse on every axis the request cares about. **So: a bound stays.** What
changes is that it stops being an opinion about how many rules files a judge ought
to need, and becomes a statement of how many will fit.

## 3. The bound: what is left of the window

```
budget = window_tokens x CHARS_PER_TOKEN
       - max_tokens x CHARS_PER_TOKEN        # the completion has to fit too
       - max(move_reserve, round_reserve, game_reserve)
       - PROMPT_FRAME_CHARS
       - len(prompt_override)
       - sum(len(SKILL.md) for each selected skill)
```

floored at zero, where the three scope reserves are

| scope | state | move context | roll-up context |
| --- | --- | --- | --- |
| move | 2 x `max_state_chars` | (`before` + `after`) x (`reasoning_chars` + `MOVE_BLOCK_OVERHEAD_CHARS`) | — |
| round | `max_state_chars` | `max_round_moves` x (same) | `max_round_moves` x (`child_rationale_chars` + `CHILD_BLOCK_OVERHEAD_CHARS`) |
| game | `max_state_chars` | — | `max_round_moves` x (same) |

**A max, not a sum.** One judge configuration serves all three prompt shapes, and
they hold different things: a move prompt has two states and a neighbour block
but no roll-up context; a round prompt has one state, a move list and its moves'
verdicts; a game prompt has one state and its rounds' verdicts. Summing them
reserves for a prompt the service cannot build, and would refuse selections that
fit every prompt it can.

At the defaults (`128,000` window, `1,024` max tokens, `20,000` state chars,
`100` round moves, `100`+`100` move context, `400` reasoning chars, `600` child
rationale chars) the **move** prompt binds:

| term | chars |
| --- | --- |
| window | 512,000 |
| less completion (1,024 x 4) | -4,096 |
| less two states (2 x 20,000) | -40,000 |
| less neighbours (200 x (400+400)) | -160,000 |
| less prompt frame | -12,000 |
| **budget, before skills** | **295,904** |

The round prompt's reserve is 20,000 + 100 x 800 + 100 x 800 = 180,000, and the
game prompt's 20,000 + 80,000 = 100,000, so both fit inside the move prompt's
200,000 with room to spare.

### Every term is a setting that already existed

This is the property that makes the derivation defensible rather than another
invented number. The reserve is not a guess about the prompt; it is the prompt's
own configured ceilings, read back. An operator who finds the budget too tight has
a real lever in each direction, and each lever does the thing its name says:

- `EVAL_JUDGE_CONTEXT_WINDOW_TOKENS` — tell the service the window your judge
  model actually has. A 1M-context model raises the budget to ~3.8M characters,
  which is twelve times the entire shipped corpus.
- `EVAL_JUDGE_MOVE_CONTEXT_BEFORE` / `_AFTER` — the largest reserve term by far,
  and what makes the move prompt the binding scope. These are documented in
  `config.py` as *safety backstops*, not the mechanism: "a move is judged in the
  context of ITS ROUND", and a real Marvel Champions round is 6-10 moves, not 200.
  An operator who lowers them to 25 each recovers 120,000 characters of budget and
  loses nothing a real round uses.
- `EVAL_JUDGE_MAX_STATE_CHARS` — 40,000 characters across two states.
- deselect a `SKILL.md`, which is charged at its real size.

### Three constants are projections, and are named as such

- `MOVE_BLOCK_OVERHEAD_CHARS = 400`. A move line is
  `- seq N: action=<json> args=<json> reasoning=<clipped>`. The reasoning is
  clipped by a setting; `args` is **not**, deliberately — legality is judged on a
  move's arguments and truncating them would change verdicts — so this covers the
  line text, the action name and a projected arguments object, not a ceiling.
- `CHILD_BLOCK_OVERHEAD_CHARS = 200`. The label, span and score of one roll-up
  child verdict, whose rationale *is* clipped.
- `PROMPT_FRAME_CHARS = 12,000`. The rubric measures 1,526 characters and the
  orchestrated-mode note 468; the remainder covers section labels, the round's
  illegal-action findings, and the graded move's own action/arguments/reasoning
  block, which is never clipped because it is the thing being judged.

All three are deliberately generous. They over-reserve, which makes the budget
*conservative*: it can refuse a selection that would in fact have fitted, and it
must not accept one that would not. This is stated here rather than buried because
it is the only place the derivation is not exact.

### A per-item clip of `0` must not raise the budget

`prompt._clip` treats `0` as "do not clip". Reserving `0` for a field configured
that way would move the reserve the wrong way — the text becomes unbounded and
the budget *grows* — so `_clip_reserve` substitutes
`UNCLIPPED_TEXT_PROJECTION_CHARS = 2,000` instead. Turning a clip off now costs
budget, which is the direction that matches what it does.

## 4. Making the reserve a real ceiling: two unbounded prompt terms

The derivation above is only worth anything if the prompt actually honours the
caps it reserves against. Two terms did not, and both live in the scopes the old
60,000-character budget left ~236,000 characters of slack to absorb. Raising the
budget to consume that slack is exactly what exposes them, so they are fixed here
rather than filed:

- **A round roll-up's move list rendered `reasoning` unclipped.**
  `build_round_messages` emitted `reasoning={_json(move.reasoning)}` with no cap
  and did not even take one, while `_neighbour_block` clips *the same field* for
  the stated reason that "one verbose neighbour cannot bloat a prompt". Recorded
  reasoning is whatever the playing agent wrote; at 100 moves this term alone can
  exceed the entire reserve. It now clips at
  `EVAL_JUDGE_MOVE_CONTEXT_REASONING_CHARS`, which is the cap the reserve already
  assumed.
- **Roll-up child verdicts were unbounded in both count and size.** A round
  carries one child per graded move and a game one per round; neither the
  recording side nor `_child_context_block` limited how many, and each carried a
  full judge-authored rationale. The count is now capped at
  `EVAL_JUDGE_MAX_ROUND_MOVES` — the same ceiling the move list uses, with the
  same "N further omitted" line — and each rationale at a new
  `EVAL_JUDGE_MAX_CHILD_RATIONALE_CHARS`, default 600. The rubric asks the judge
  for "a short rationale paragraph", so 600 is generous for one.

This changes round and game prompt bytes when a move's reasoning exceeds 400
characters or a rationale exceeds 600. It does **not** touch
`judge_config_digest` (which hashes the config, not the prompt), so nothing stops
deduplicating, and it does not touch `_system_content`, so §8's byte-identity
guarantee is unaffected.

Two smaller terms remain projections rather than ceilings and are charged to
`PROMPT_FRAME_CHARS` / `MOVE_BLOCK_OVERHEAD_CHARS`: a move's `arguments`, which
must not be clipped, and `_illegal_action_block`, which is bounded in practice by
the findings one round can hold.

### `len(prompt_override)` is added on top of the frame, not swapped for the rubric

An override *replaces* the 1,526-character rubric, so charging both double-counts
1,526 characters against a 50,000-character maximum override. Accepted: the error
is small, always in the conservative direction, and the alternative
(`frame - RUBRIC + override`) makes the arithmetic in the refusal message harder
to follow for 0.3% of a window.

### Why not fetch the real context length from Bifrost

The orchestrator does exactly that — `get_model_context_length` reads
`context_length` off `/v1/models` and falls back to `CONTEXT_WINDOW_SIZE`
(`api/routers/context.py:33`). Copying the pattern was considered and rejected:

- eval-service's `BifrostJudgeClient` has **no** models listing at all. Its only
  non-judge method is `named_key_providers`. Adding one is new network surface.
- `resolve_judge_config` is **synchronous**, called from `RequestService.create`
  and from `Evaluator`. Making the budget depend on a live HTTP call means making
  it async and threading that through both call sites.
- The call would sit in the *request-rejection* path. When Bifrost is unreachable
  — which is its state on this stack right now — the lookup either fails the
  request (a selection refused because a *gateway* was down) or silently falls
  back, so the number the user is told is sometimes live and sometimes not, with
  no signal which.
- **It cannot be verified here.** No key, no provider available. Shipping async
  plumbing whose only interesting behaviour is unobservable is how a bug gets
  merged with a green suite.

A single configured window is exact, testable, and honest about what it is. If a
live lookup is wanted later it slots in behind the same function.

## 5. `EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS` becomes a floor-only knob

It survives, with a changed default and a changed meaning:

| value | before | after |
| --- | --- | --- |
| `0` | budget disabled entirely | no cap beyond the window (**new default**) |
| `> 0` | the budget | an *additional* cap: `min(derived, value)` |
| `< 0` | refused | refused (unchanged) |

Three deliberate choices.

**The default moves from 60,000 to 0.** Leaving it at 60,000 while adding a
derived budget would change nothing at all — `min(295904, 60000)` is 60,000 — and
would ship a change that reads like a fix and behaves like the bug.

**A positive value can only lower, never raise.** The old setting could be set to
1,000,000, which bought nothing but a provider error later. The window is not
negotiable by a character setting; it is negotiable by
`EVAL_JUDGE_CONTEXT_WINDOW_TOKENS`, where the negotiation is a statement about the
model rather than a wish about the budget.

**`0` stops meaning "unbounded".** This is a semantic change to a setting DRA-41
shipped hours ago, and it is called out in the spec delta and the README rather
than left for someone to discover. "Unbounded" was never a state the service could
honour: the window bounds it whether the setting acknowledges it or not, so the
option only ever let an operator choose *where* the failure surfaced. Removing it
removes a foot-gun, not a capability. A negative value is still refused, for
DRA-41's original reason: it reads like a tight limit and would behave like none.

## 6. The count bound: 8 becomes 1,000, and stops being a policy

A count is the wrong instrument. Eight references drawn from
`marvel-champions-rules-reference` range from `resources/errata.md` at 38,515
characters to files under 2,000 — a 20x spread. A count bound therefore refuses a
selection it should allow and allows one it should refuse, at whatever number it
is set to. Size is the only bound that measures the thing that matters, and there
is now one.

What the count ceiling is *for*, after this change, is stopping an absurd request
body before anything is read from disk: 100,000 selection strings would be 100,000
`parse_reference_selection` calls and, if valid, 100,000 file reads before the
budget check could trip. `MAX_SELECTION_LIST = 1000` already plays exactly this
role for target selections in the same schema, so `MAX_SKILL_REFERENCES` joins it
at 1,000 rather than inventing a third scale.

Against 28 shipped reference files, 1,000 is unreachable by any selection a person
or a "select all" button can make — the request "as many as I want, not only 8" is
satisfied in full. If the corpus ever approaches 1,000 files the ceiling is one
constant, and the budget will have refused the selection long before the schema
does.

## 7. Refusing has to teach, because the dashboard cannot see sizes

The dashboard offers "select all" over a catalogue that reports reference
**names** only — `GET /skills` returns `references: list[str]`, with no size.
Adding sizes means an orchestrator API change, a schema change, and a second
consumer to keep in sync; it is not in this change. The consequence is that the
user *can* click "select all" into a selection the server refuses, and the refusal
is the only place they learn why.

So the refusal carries the whole derivation:

```
selected skill references total at least 313,317 characters, over the 204,549
character budget by 108,768; references are never truncated. A 128,000-token
context window is ~512,000 chars at ~4 chars/token; reserving 4,096 for the
completion, 40,000 for game state, 160,000 for round context, 0 for roll-up
context, 12,000 for the prompt frame (worst case is the move prompt), 0 for the
prompt override and 91,355 for 5 selected SKILL.md file(s) leaves 204,549.
Deselect references or skills, lower EVAL_JUDGE_MOVE_CONTEXT_BEFORE /
EVAL_JUDGE_MOVE_CONTEXT_AFTER or EVAL_JUDGE_MAX_STATE_CHARS, or set
EVAL_JUDGE_CONTEXT_WINDOW_TOKENS to your judge model's real context window.
```

The reserve breakdown is present **whether or not an operator cap is what bit** —
when `EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS` lowers the budget, one further
sentence says so and the terms stay, because the terms are what name the settings
to change.

Every number in it is a term the user can act on, and the largest reserve terms
name the settings that shrink them. It is verbose on purpose: it is shown once, at
the moment the user is blocked, and the alternative to reading it is not knowing
why all 21 rules references fit and 28 references plus five skills did not. DRA-41
already
made this legible in the dashboard by flattening FastAPI's validation `detail`
array, and this message rides the same 400 path as the old one
(`SkillReferenceBudgetError` -> `RequestError` -> 400), so no client change is
needed to display it.

**Truncation is still refused, and this change does not reopen it.** DRA-41's
reason holds exactly: a clipped board is still a board, but a clipped rules
reference reads to the judge like a complete one, and grading against two thirds
of the errata with no way to tell is the defect the whole path exists to fix.

## 8. Nothing an existing evaluation depends on moves

- `_system_content` is untouched. A reference-free config still produces
  byte-identical bytes; `test_a_reference_free_prompt_is_byte_identical` still
  guards it.
- `ResolvedJudgeConfig.to_json` is untouched, so `judge_config_digest` and every
  idempotency key are unchanged. The budget is a *gate* on what may be selected,
  not part of what is hashed — two identical selections graded under different
  budgets are the same config and must keep deduplicating.
- `EVALUATOR_VERSION` stays `eval-2`, for DRA-41 §5's argument, which this change
  does not disturb: the difference a reference selection makes is already
  described by the digest.

## Follow-ups, deliberately not here

- **Reference sizes in the catalogue.** `GET /skills` reporting bytes per
  reference would let the dashboard show a live budget meter and grey out a
  "select all" that cannot fit, turning the 400 into something the user never
  hits. It is an orchestrator schema change with its own consumers.
- **Bounding a move's `arguments`.** The last unclipped field of any size in the
  judge prompt, and the reason `MOVE_BLOCK_OVERHEAD_CHARS` is a projection rather
  than a ceiling. Deliberately left alone: legality is judged on a move's
  arguments, so clipping them changes verdicts, which is a grading decision rather
  than a budget one.
- **A "select all" the dashboard can size.** At the stock defaults, selecting
  every reference of every skill is refused — 404,672 characters of references
  and `SKILL.md` against a 295,904 budget. The single reason is the 160,000-char
  move-context reserve for 200 neighbours, a shape `config.py` itself calls a
  safety backstop against a round that is really 6-10 moves. Lowering that default
  would make the whole corpus fit out of the box, but it is a DRA-10 grading
  decision, not this change's to make.
- **A live per-model window lookup**, per §3, once there is a key to verify it
  against.
