# The judge can read a skill's reference files, not just its SKILL.md

## Why

DRA-41 reports two things about the evaluator's access to rules skills:

> By default the evaluator load a whole skill content into system prompt. It could
> be replaces with `load_skill` tool, like for agents.

> The evaluator don't have a possibility to load the skill references right noww.

The second is a defect, and it is the one that changes verdicts. A skill's
reference files are part of its content. `marvel-champions-rules-reference` is
18,306 bytes of `SKILL.md` and **256,568 bytes across 21 reference files** — the
errata, the FAQ, the A-Z glossary, the timing rules. `eval-service`'s
`SkillResolver` can resolve a skill name to its `SKILL.md` and nothing else:
there is no `list_reference_files`, no `load_reference_content`, and
`_system_content` appends only the `SKILL.md` body. A judge selecting the rules
skill therefore grades every move against **6.7% of the rulebook it was pointed
at** and has no way to reach the rest. It cannot check an errata'd card, cannot
resolve a timing question, and — worst — cannot tell that it is missing any of
this, so it grades confidently against a partial rulebook.

The first is framed as an option ("could be replaced"), and this change declines
it, for reasons argued in `design.md` and summarised here:

- **The judge has no tool loop.** `BifrostJudgeClient._build_payload` sends
  `{model, messages, max_tokens}` with no `tools` key; `judge()` returns
  `choices[0].message.content`; `judge_stream()` yields text deltas;
  `Evaluator._call_judge` makes exactly one call and `parse_verdict` demands a
  single JSON object. Nothing in `eval-service` parses `tool_calls`. Giving the
  judge `load_skill` means **building a tool-calling loop**, which is a larger
  change than the issue implies and is proposed separately rather than smuggled
  in here.
- **Lazy loading is the wrong shape for a judge even with a loop.** An agent's
  skill need varies by situation, so paying a round trip to fetch only what this
  turn needs is a win. A judge runs the *same* rubric against the *same* rules
  for every target: the tool would return identical bytes on every call, turning
  a cacheable static prefix into a dynamic one. Worse, a single-shot judge that
  *declines* to call the tool still emits a well-formed verdict — it fails open,
  silently, and the verdict looks exactly like a good one. And because a
  verdict's history identity is a hash of the resolved judge config, a
  model-chosen set of loaded skills would break the property that the config
  identifies what the judge actually saw.

So: keep inlining `SKILL.md`, and give references the same explicit, config-level
treatment — deterministic, hashed into the verdict's identity, and capped.

## What Changes

- **`eval-service` resolves skill references.** A new `judge.skill_references`
  field on the evaluation request takes `"<skill-name>/<relative-path>.md"`
  entries. Each is resolved under the configured skill roots and inlined into the
  judge system prompt beneath the skill it belongs to.
- **Reference resolution is path-safe by construction.** A caller-supplied
  reference path is confined to its own skill directory: absolute paths, `..`
  traversal, symlinks that leave the skill, non-`.md` files, directories and
  `SKILL.md` itself are all refused. The rules live in one helper with tests for
  each refusal.
- **Selections are bounded, and refuse rather than truncate.** At most 8
  references per request (schema-level), and a total reference budget
  (`EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS`, default 60,000 chars) enforced when
  the request is resolved. Over budget is a 400 with the measured size, not a
  silently clipped rulebook — a truncated rulebook is the same defect this change
  exists to fix.
- **References are discoverable.** The agent-orchestrator's `GET /skills` gains a
  `references` list per skill, so the dashboard's judge panel can offer the real
  reference names of the selected skills instead of requiring the operator to
  know them.
- **The dashboard judge panel offers them.** Selecting a skill in the Evaluate
  panel reveals its reference files as individually selectable entries, assembled
  into `judge.skill_references`.
- **Nothing about an existing evaluation changes.** For every judge config
  expressible before this change (i.e. one with no reference selections) the
  system prompt is byte-identical and the resolved-config digest is unchanged, so
  existing idempotency keys still dedupe and existing `eval-2` verdicts stay
  comparable. `EVALUATOR_VERSION` is deliberately not bumped; `design.md` argues
  it.

## Impact

- Affected specs: `agent-move-evaluation`, `agent-orchestrator`, `dashboard`
- Affected code:
  - `services/eval-service/src/eval_service/judge/skill_resources.py` (new)
  - `services/eval-service/src/eval_service/judge/config.py`
  - `services/eval-service/src/eval_service/judge/prompt.py`
  - `services/eval-service/src/eval_service/judge/writeback.py`
  - `services/eval-service/src/eval_service/runtime/evaluator.py`
  - `services/eval-service/src/eval_service/runtime/requests.py`
  - `services/eval-service/src/eval_service/schemas/api.py`
  - `services/eval-service/src/eval_service/config.py`
  - `services/agent-orchestrator/src/agent_orchestrator/schemas/catalog.py`
  - `services/agent-orchestrator/src/agent_orchestrator/api/routers/catalog.py`
  - `services/dashboard/features/history/lib/judge-config.ts`
  - `services/dashboard/features/history/components/judge-config.tsx`
  - `services/dashboard/features/shared/lib/types.ts`
- Not affected: the `judge` provider call shape, the SSE token stream, the
  verdict payload schema, `EVALUATOR_VERSION`.
