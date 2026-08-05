# The judge's reference selection is bounded by the context window, not by a count of 8

## Why

DRA-54 asks for two things:

> I should have option to a) select all b) select as many as i want, not only 8.

DRA-41 shipped reference selection this morning with two bounds: a schema-level
ceiling of **8 references** per request, and a **60,000-character** total budget
(`EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS`). Both refuse rather than truncate, which
was and remains right. Neither number, however, is derived from anything.

The measurement that decides this change is that **the bounds are far below what
the judge can physically carry.** On-disk bytes under `skills/` at this base
commit:

| skill | `SKILL.md` | reference files | reference bytes |
| --- | --- | --- | --- |
| `dragncards` | 16,731 | 0 | 0 |
| `marvel-champions-learn-to-play` | 32,301 | 0 | 0 |
| `marvel-champions-orchestrator` | 14,053 | 2 | 18,464 |
| `marvel-champions-play` | 9,964 | 5 | 38,285 |
| `marvel-champions-rules-reference` | 18,306 | 21 | 256,568 |
| **all five** | **91,355** | **28** | **313,317** |

At the ~4-chars-per-token rule of thumb DRA-41 used — **a projection, not a
measurement; see "What could not be verified"** — a 128,000-token window holds
roughly 512,000 characters. The judge's non-reference prompt is bounded by
settings that already exist and totals ~216,000 characters at their defaults. So
about **296,000 characters** of reference content fit. The whole 21-file rules
corpus is 256,568, and its `SKILL.md` another 18,306. **"Select all the rules
references" fits, and both of DRA-41's bounds forbade it** — the count bound at
reference nine, the size bound at 60,000 characters, which is 12% of the window
and 20% of what actually fits.

So the constraint was not physics. It was a placeholder standing where a derived
number belonged, and the owner is right that it is in the way.

**A bound does remain, and `design.md` argues why it must.** A prompt larger than
the model's window does not degrade, it fails outright — DRA-33 measured this on
the agent side today, where the real request reached 132,551 tokens against a
128,000-token window. Removing the bound entirely would convert DRA-41's clean,
pre-enqueue 400 into a provider error arriving per-target after the batch is
running. That is strictly worse for the user. The fix is to make the bound *equal
the physics* and *say so when it refuses*, not to delete it.

## What Changes

- **The count bound stops being a selection policy.** `MAX_SKILL_REFERENCES` goes
  from 8 to 1,000, joining `MAX_SELECTION_LIST` as a request-body sanity ceiling
  no real selection approaches — 28 reference files ship in total. There is no
  longer any count at which a human selection is refused.
- **The size bound is derived from the judge model's context window.** A new
  `EVAL_JUDGE_CONTEXT_WINDOW_TOKENS` (default 128,000, mirroring the
  orchestrator's `CONTEXT_WINDOW_SIZE`) is converted to characters and reduced by
  what the rest of the prompt can occupy at the *already configured* caps: the
  completion reserve (`EVAL_JUDGE_MAX_TOKENS`), and then the **worst** of the
  three scope reserves — move, round and game prompts hold different things, so
  the reserve is a max rather than a sum — plus a fixed prompt frame, the prompt
  override, and the `SKILL.md` files this very request selected. What is left is
  the reference budget: **295,904 characters** at the defaults, **4.9x** the old
  60,000.
- **Two unbounded prompt terms are bounded, so the reserve is a real ceiling.** A
  round roll-up rendered each move's `reasoning` unclipped — the same field a
  move prompt's neighbour block has always clipped — and rendered one child
  verdict per graded move with an unbounded rationale and no count limit. Left
  alone, either could outweigh the whole reserve and turn the new, larger budget
  into the provider error this change exists to prevent. The move list now clips
  at `EVAL_JUDGE_MOVE_CONTEXT_REASONING_CHARS`, and child verdicts are bounded by
  count (`EVAL_JUDGE_MAX_ROUND_MOVES`) and by a new
  `EVAL_JUDGE_MAX_CHILD_RATIONALE_CHARS` (600).
- **`EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS` changes meaning and default.** It
  becomes an optional *additional* cap, default `0` = "no cap beyond the window".
  A positive value only ever lowers the derived budget; it can no longer raise it
  above the window, because raising it above the window never worked. Raising the
  budget is now done by telling the service the window your judge model actually
  has. `0` no longer means "unbounded" — it means "bounded by physics alone".
- **The refusal names the arithmetic.** The 400 states the measured total, the
  budget, the overage, every term of the reserve that produced the budget (and
  which scope was the worst case), and the settings that would change it. A user
  who selects all 28 references alongside all five `SKILL.md` files is told they
  are 108,768 characters over and exactly what to drop.
- **The dashboard gets "select all".** The `n/8` counter and the disabling of
  unselected rows are gone. The header carries a "Select all" / "Clear all" pair
  over every reference of every selected skill, and each skill group carries its
  own "All" / "None" — a 21-file skill and a 2-file skill are one click each.
- **Nothing about an existing evaluation changes.** A judge config selecting no
  references still produces a byte-identical system prompt and an unchanged
  `judge_config_digest`, so `eval-2` verdicts keep deduplicating.
  `EVALUATOR_VERSION` is not bumped, for the reasons DRA-41 recorded.

## Impact

- Affected specs: `agent-move-evaluation`, `dashboard`
- Affected code:
  - `services/eval-service/src/eval_service/judge/reference_budget.py` (new)
  - `services/eval-service/src/eval_service/judge/config.py`
  - `services/eval-service/src/eval_service/judge/prompt.py`
  - `services/eval-service/src/eval_service/runtime/evaluator.py`
  - `services/eval-service/src/eval_service/schemas/api.py`
  - `services/eval-service/src/eval_service/config.py`
  - `services/eval-service/README.md`, `services/eval-service/AGENTS.md`,
    `services/eval-service/.env.example`, `docker-compose.yaml`
  - `services/dashboard/features/history/components/judge-skill-references.tsx`
  - `services/dashboard/features/shared/lib/types.ts`
- Not affected: `judge/skill_resources.py` and its path-safety rules, the
  refuse-rather-than-truncate rule for reference content, `_system_content`, the
  `judge` provider call shape, the SSE token stream, the verdict payload schema,
  `judge_config_digest`, `EVALUATOR_VERSION`.

## What could not be verified

`EVAL_JUDGE_OPENROUTER_API_KEY` is unset on this stack and the service reports
`judge_configured: false`, so **no judge call can be made and no prompt or
completion token count was measured.** Every token figure in this change and in
`design.md` is a projection at ~4 characters per token, the convention DRA-41
established and labelled the same way. The character counts *are* measured, from
the files on disk at this commit.
