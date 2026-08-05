# DRA-54 handoff — "Remove skill reference limit for reviewer"

Branch `stanislaw/dra-54-reference-budget-from-context-window`, worktree
`/home/kanareklife/Projects/.dragncards-wt/wt-dra54`, based on `7a2dd5c`.

**Status: complete and green.** Nothing is half-done. Not pushed, no PR, the
OpenSpec change is deliberately NOT archived.

## The request

> I should have option to a) select all b) select as many as i want, not only 8.

## What was decided about DRA-41's two bounds

**The count bound of 8 is gone as a policy.** A count measures nothing here: the
21 files of `marvel-champions-rules-reference` span a 20x size range (38,515
chars down to under 2,000), so any count refuses selections it should allow and
admits ones it should refuse. `MAX_SKILL_REFERENCES` is now **1,000**, at
`MAX_SELECTION_LIST`'s scale, and exists only to reject an absurd request *body*
before anything is read from disk. 28 reference files ship in total, so "select
all" is 28 and no human selection can reach it. A per-entry
`MAX_SKILL_REFERENCE_LENGTH = 512` was added alongside it.

**The 60,000-character budget is gone as a fixed number.** It was 12% of a 128k
window. The judge's whole non-reference prompt, once bounded, is ~216,000 chars,
so ~296,000 chars of references fit — the old bound left ~236,000 characters of
window unused on every evaluation. It was not protecting anything.

## A bound remains, and this is the physics

The judge is single-shot — `_build_payload` sends no `tools` key, `parse_verdict`
demands one JSON object, nothing reads `tool_calls` — so **every selected byte is
in the prompt, always**, and there is no tool loop that could fetch on demand.

A prompt over the model's window does not degrade, it is a provider error. DRA-33
measured this on the agent side today: 132,551 tokens against a 128,000-token
window. Removing the bound entirely would trade one clean 400 at request time,
before any target is enqueued, for a batch that is accepted and then fails *per
target* inside the worker with a gateway-authored message, paying
`EVAL_MAX_ATTEMPTS` retries on the way. That is worse on every axis the request
cares about.

So the bound stays, but it now **equals the physics**:

```
budget = EVAL_JUDGE_CONTEXT_WINDOW_TOKENS x 4          # 512,000 at the default
       - EVAL_JUDGE_MAX_TOKENS x 4                     # -4,096
       - max(move, round, game scope reserve)          # -200,000 (move binds)
       - PROMPT_FRAME_CHARS                            # -12,000
       - len(prompt_override) - selected SKILL.md bytes
```

**295,904 characters at the defaults — 4.9x the old 60,000.** The reserve is a
`max` over the three scopes, not a sum: a move prompt has two states and a
neighbour block but no roll-up context; a round prompt has one state, a move list
and its moves' verdicts. Summing them reserves for a prompt that cannot exist.

Every reserve term is a setting that already existed, so an operator has a real
lever: `EVAL_JUDGE_CONTEXT_WINDOW_TOKENS` (new, default 128,000, mirrors the
orchestrator's `CONTEXT_WINDOW_SIZE`) raises it;
`EVAL_JUDGE_MOVE_CONTEXT_BEFORE`/`_AFTER` are the largest term by far and are
documented in `config.py` as backstops against a round that is really 6-10 moves,
not 200.

`EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS` survives with a **changed default (0) and
changed meaning**: `0` = no cap beyond the window, `> 0` = an additional cap that
only ever *lowers* the derived budget, `< 0` still refused. It can no longer raise
the budget above the window, because that only ever bought a provider error later.
`0` no longer means "unbounded" — that was never a state the service could honour.

### What this buys, in measured characters

| selection | chars | verdict |
| --- | --- | --- |
| all 21 rules references + their `SKILL.md` | 274,874 | **accepted** (was refused twice over) |
| all 28 references, no skills | 313,317 | refused by 17,413 |
| all 28 references + all 5 `SKILL.md` | 404,672 | refused by 108,768 |

The refusal states the measured total, the budget, the overage, every reserve
term, which scope was the worst case, and the settings that would change it —
whether the window or an operator cap produced the budget. The dashboard's
catalogue reports reference *names* only, so this 400 is the only place a user
learns why "select all" did not fit.

## Contradicting the brief I was given

The brief suggested removing the count bound but keeping a size bound "derived
from the model's actual context window", and floated fetching that window live.
Two things came out differently:

1. **No live Bifrost lookup.** eval-service's `BifrostJudgeClient` has no models
   listing at all (only `named_key_providers`), `resolve_judge_config` is
   synchronous and called from two places, and the call would sit in the
   request-*rejection* path — so an unreachable gateway would refuse a selection.
   It is also unverifiable here (no key). A configured window is exact and
   testable; the design records this and files the live lookup as a follow-up.

2. **The brief's projection that "select all" would fit was wrong, and so was my
   own first draft.** The adversarial review caught a genuine blocking defect: the
   reserve modelled only the *move* prompt. `build_round_messages` rendered each
   move's `reasoning` **unclipped** (the same field `_neighbour_block` has always
   clipped) and did not even take a cap, and `_child_context_block` rendered
   roll-up child verdicts with **no count limit and no rationale limit**. Under the
   old 60,000 budget ~236,000 chars of slack absorbed both; raising the budget is
   exactly what exposes them. So this change also bounds them — that work is
   commit `138874d`, and it is why the budget is 295,904 rather than the ~340,000
   the first draft claimed. Selecting *every* reference of *every* skill still does
   not fit a 128k window, and the design says so plainly rather than pretending.

## What is implemented

- `services/eval-service/src/eval_service/judge/reference_budget.py` (new) — the
  derivation, the `ReferenceBudget` dataclass carrying every term, and the refusal
  message. A per-item clip of `0` ("do not clip") reserves
  `UNCLIPPED_TEXT_PROJECTION_CHARS` so switching a clip off cannot *raise* the
  budget.
- `judge/config.py` — `load_references` takes a `ReferenceBudget`;
  `resolve_judge_config` keeps the `SKILL.md` content it already loaded and charges
  its size.
- `judge/prompt.py` — round move `reasoning` clipped at
  `EVAL_JUDGE_MOVE_CONTEXT_REASONING_CHARS`; `_child_context_block` bounded by
  count (`EVAL_JUDGE_MAX_ROUND_MOVES`, with an omission line and a log) and by a
  new `EVAL_JUDGE_MAX_CHILD_RATIONALE_CHARS` (600). A move's `arguments` stay
  unclipped on purpose — legality is judged on them.
- `runtime/evaluator.py` — passes the new caps; re-derives the same budget.
- `schemas/api.py`, `config.py`, `.env.example`, `docker-compose.yaml`.
- Dashboard `judge-skill-references.tsx` — count cap and row-disabling gone;
  header "Select all"/"Clear all", per-group "All"/"None", counter now
  `selectedHere/total`. `types.ts` comment corrected.
- OpenSpec change `openspec/changes/dra-54-reference-budget-from-context-window/`
  with proposal, design, tasks (all ticked) and deltas for
  `agent-move-evaluation` and `dashboard`. No `TBD`/`TODO`.

**Not touched, verified by diff:** `judge/skill_resources.py` and all its
path-safety rules, `_system_content`, `ResolvedJudgeConfig.to_json`,
`judge_config_digest`, `EVALUATOR_VERSION` (still `eval-2`).

## Tests run, with exact counts

Unit (`./scripts/test.sh unit`) — all pass:

| service | count | baseline on `7a2dd5c` |
| --- | --- | --- |
| eval-service | **356** | 340 (+16) |
| dashboard | **684** | 678 (+6) |
| agent-orchestrator | 652 | 652 |
| game-service | 476 | 476 |
| history-service | 202 | 202 |
| shared | 38 | 38 |

Integration (`./scripts/test.sh integration`): game-service 66,
agent-orchestrator 31, history-service 8, eval-service 17 — all at baseline.

`./scripts/lint.sh --fix` clean. `pnpm typecheck` in `services/dashboard` clean.
`openspec validate --all`: 17 passed, 1 failed — only the pre-existing
`spec/typed-game-actions`.

New eval-service tests were verified to FAIL on the base commit by stashing
`services/eval-service/src` and re-running.

## Verification I could NOT do

**No judge call is possible.** `EVAL_JUDGE_OPENROUTER_API_KEY` is unset,
`judge_configured` is `false`, every provider reads `available=false`, and no
tokenizer is installed in `services/eval-service/.venv`. **Every token figure in
this change is a projection at ~4 chars/token**, labelled as such everywhere, per
DRA-41's convention. The character counts *are* measured, from `skills/` at this
commit. `MOVE_BLOCK_OVERHEAD_CHARS`, `CHILD_BLOCK_OVERHEAD_CHARS` and
`PROMPT_FRAME_CHARS` are deliberately generous projections, not ceilings, because
a move's `arguments` remain unclipped.

The dashboard control was driven in a real headless Chromium against a stub
backend on ports 39110/39120 (both stopped): 12 references ticked one at a time
with no row ever disabled, `14/14` via Select all, `0/14` via Clear all, group
All/None confirmed scoped. No console errors. One aesthetic nit noted and not
fixed: the ghost buttons render at 14px beside an 11px group label.

## Precise next step

Nothing is outstanding for the implementation. To resume:

1. Re-run the three commands above to confirm the tree is still green.
2. Open the PR from the integration branch when the owner asks — **the PR is
   always the owner's call, and this branch has not been pushed.**
3. Archive `openspec/changes/dra-54-reference-budget-from-context-window` and sync
   `openspec/specs/agent-move-evaluation` and `openspec/specs/dashboard` only as
   part of the merge step, not here.

Three follow-ups are argued in `design.md` and are intentionally out of scope:
reference **sizes** in the orchestrator's `GET /skills` (which would let the
dashboard size "select all" before the request and turn the 400 into something the
user never hits), bounding a move's `arguments`, and a live per-model window
lookup once there is an API key to verify it against.
