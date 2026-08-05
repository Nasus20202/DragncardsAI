# Design: judge access to skill reference files

## Context

Two questions, in the order they have to be answered.

1. Does the judge's provider loop support tool calls? This decides the shape of
   everything else.
2. Given the answer, how should a judge reach a skill's reference files?

## 1. The judge is a single-shot completion. There is no tool loop.

Established by reading the call path on this base commit, not by assumption:

- `BifrostJudgeClient._build_payload`
  (`services/eval-service/src/eval_service/integrations/bifrost.py`) builds
  `{"model", "messages", "max_tokens"}` and then `payload.update(gateway_options)`,
  where `gateway_options` is only ever
  `ResolvedReasoning.to_gateway_options()` — `{}` or `{"reasoning": {...}}`. There
  is no `tools` key and no way to pass one.
- `BifrostJudgeClient.judge()` returns the assistant message *content*.
  `judge_stream()` yields text deltas. Neither reads `tool_calls`.
- `Evaluator._call_judge` makes exactly **one** call per attempt and returns a
  string. `Evaluator._produce_verdict` hands that string straight to
  `parse_verdict`, which requires a single JSON verdict object.
- `grep -rn "tool_calls\|tools" services/eval-service/src` finds nothing in the
  judge path.

The class docstring states the invariant deliberately: *"Every call is a FRESH,
stateless chat completion... No session is reused: each invocation sends only the
supplied messages."*

**Therefore "replace inlining with `load_skill`" means building a tool-calling
loop inside eval-service.** Concretely that is: a tool-schema surface; multi-turn
message accumulation across the loop; `tool_calls` parsing from *both* the
non-streaming and the streaming Bifrost response shapes; a tool-round cap with a
terminal outcome when it is hit; reconciling the loop with the existing
per-attempt retry (an attempt that fails after three tool round trips must not
replay the tool results into a second conversation); and reconciling it with the
SSE contract, where the dashboard concatenates text deltas with no reset signal
(`_produce_verdict` already suppresses streaming on retries for exactly this
reason). That is a change on the scale of the retry/streaming work itself, and it
is **not** in this change. It is proposed as a separate issue — see
"Follow-up: a judge tool loop" below.

## 2. Inlining `SKILL.md` is the right default for a judge. References are not.

This is not only "the cheaper option". Four reasons, in order of weight.

### 2a. Verdict identity should stay as close to the evidence as it can

`verdict_idempotency_key` hashes the resolved judge config
(`judge_config_digest`), so an identical re-evaluation dedupes and a re-evaluation
under a different judge does not.

**The limit has to be stated honestly, because it is not what it first looks
like.** The digest hashes the *selection*, not the *content*. The files are read
at request time in `resolve_judge_config` and read again at judge time in
`Evaluator._produce_verdict`, potentially much later and in another process; edit
`resources/errata.md` in between and two evaluations under a byte-identical config
see different rules while colliding on one idempotency key. That window is
pre-existing for `skills`, and this change widens it across the reference corpus —
which is precisely the material most likely to be edited, since errata get
errata'd. (It is also why the resolver does **not** cache reference content: a
process-lifetime cache would turn that window into a permanent one.)

Folding a content hash into the digest would close it, and is deliberately not
done: the digest would then move whenever any skill file changed, destroying the
§5 guarantee that an already-recorded verdict keeps deduplicating. The selection
is the stable identity; the content is not.

So the argument against a tool loop here is **comparative, not categorical**.
With inlining, the config pins the selection, and only an out-of-band file edit —
an operator action, visible in a deploy — can desynchronise it from the content.
With a tool loop the *selection itself* becomes non-deterministic: the model
chooses per call, so two runs of one config diverge with no external event at all,
and the key then identifies neither the content nor the selection. Strictly worse
on the same axis, which is the claim this section actually supports.

### 2b. A tool the judge can decline fails open, silently

An agent that forgets to call `load_skill` plays a bad turn, and the bad turn is
visible. A judge that forgets to call it emits a perfectly well-formed verdict
graded on no rules at all, indistinguishable from a good one. There is no output
signal to detect it. Inlining cannot fail this way: the rules are either in the
prompt or the operator did not select them.

### 2c. There is no per-turn variation for lazy loading to exploit

Lazy loading pays when the need varies: an agent in the encounter phase wants
different pages than one building a deck. A judge runs the same rubric against the
same rules for every target in a batch — a batch of 60 move targets would make 60
identical `load_skill` round trips returning identical bytes, and would convert a
static, cacheable system-prompt prefix into a dynamic one.

### 2d. The measured cost of inlining `SKILL.md` is not the bottleneck

On-disk bytes at this base commit (`skills/`, the runtime root both services
resolve against):

| skill | `SKILL.md` bytes | reference files | reference bytes |
| --- | --- | --- | --- |
| `dragncards` | 16,731 | 0 | 0 |
| `marvel-champions-learn-to-play` | 32,301 | 0 | 0 |
| `marvel-champions-orchestrator` | 14,053 | 2 | 18,464 |
| `marvel-champions-play` | 9,290 | 5 | 37,559 |
| `marvel-champions-rules-reference` | 18,306 | 21 | 256,568 |
| **all five** | **90,681** | **28** | **312,591** |

Against the rest of a judge prompt: the rubric is 1,526 chars, the orchestrated
mode note adds 468, and the two projected game states in a move prompt are each
capped at `EVAL_JUDGE_MAX_STATE_CHARS` = 20,000 — so ~41,500 chars of fixed
prompt before the round's neighbour-move block, which is itself round-sized (up to
`EVAL_JUDGE_MOVE_CONTEXT_BEFORE`/`_AFTER` = 100 moves per side, each reasoning
field clipped to 400 chars).

**Token figures below are projections at the ~4-chars-per-token rule of thumb, not
measurements.** `EVAL_JUDGE_OPENROUTER_API_KEY` is unset on this stack, every
provider reports `available=false` with 0 models, and no tokenizer for any judge
model is installed in `services/eval-service/.venv`. No judge call can be made, so
no prompt or completion token count, and no latency number, can be measured here.

- `marvel-champions-rules-reference` `SKILL.md` inlined: 18,306 chars ≈ **4.6k
  tokens**, roughly 44% of the ~41,500-char fixed prompt. Real, not free, and
  entirely ordinary next to the state payload.
- Its 21 reference files: 256,568 chars ≈ **64k tokens**, **14.0× its own
  `SKILL.md`**.
- Every skill's references at once: 312,591 chars ≈ **78k tokens**.

That ratio is the whole finding. `SKILL.md` inlining is affordable and always
wanted. The reference corpus is not inlinable wholesale under any policy — which
is precisely why the orchestrator gives *agents* `load_skill_reference` rather
than shipping references in the system prompt. A judge with no tool loop needs the
same selectivity by a different mechanism.

### Decision

Keep inlining `SKILL.md` for selected skills, unchanged and byte-for-byte. Add an
explicit, operator-chosen reference selection that is inlined the same way. The
selection is part of the judge config, so it is hashed into verdict identity,
recorded on the target row, and reproducible.

## 3. The reference selection surface

`JudgeConfig.skill_references: list[str] | None`, entries of the form
`"<skill-name>/<relative-path>.md"` — exactly the two coordinates the
orchestrator's `load_skill_reference(skill_name, reference_name)` takes, joined,
so the same reference is named the same way in both services.

Why one joined string rather than a list of objects: the field has to sort
stably inside `judge_config_digest` (which sorts list elements so a reordered
selection hashes identically, mirroring the existing `skills` handling), it has to
survive `to_json`/`from_json` round-tripping onto the target row, and it has to be
easy for the dashboard to assemble as a flat set of checkbox values. A list of
strings does all three; a list of dicts complicates all three for no gain.

A reference may be selected **without** its `SKILL.md`. "Give the judge only the
errata" is a legitimate configuration, and forcing an extra 18,306 chars to reach
a 38,515-char file would be an arbitrary tax. Rendering handles it: a skill with
references but no inlined `SKILL.md` gets its own block headed
`## Skill: <name> (references only)`, so the judge is never told it has the whole
skill when it has two files from it.

### Rendering

`_system_content` grows a third argument and keeps its existing output exactly:

```
<rubric or prompt_override>

# Rules reference skills

## Skill: marvel-champions-rules-reference

<SKILL.md body>

### Reference: resources/errata.md

<errata body>
```

With no reference selections the function emits the identical bytes it emits
today — the reference loop simply contributes nothing.

This is **measured, not argued**. The base-commit `prompt.py` and this one were
both imported into one process and driven over all three scopes (move, round,
game) crossed with four config shapes (bare rubric, prompt override, one skill,
two skills + override). The serialised message sets hash identically:

```
old sha256: df7ccc19224fa08b69299e29571cac58d49b3d36262e9be14d5399902645fd4f
new sha256: df7ccc19224fa08b69299e29571cac58d49b3d36262e9be14d5399902645fd4f
```

DRA-30's chat-mode guarantee therefore holds unchanged: `_system_content` is the
only function this change touches in that module, the mode note lives in the
*user* message and is untouched, and `test_judge_session_mode.py`'s captured
literals still pass. The permanent regression guard is
`test_a_reference_free_prompt_is_byte_identical`, which compares the prompt built
with the new argument omitted against the same prompt built with it explicitly
empty.

### Bounds, and why they refuse rather than truncate

- `MAX_SKILL_REFERENCES = 8` on the request schema (a 422 from Pydantic, matching
  how `MAX_SKILLS = 32` already behaves). Eight is above any plausible manual
  selection and far below the 21 files of the rules skill. The dashboard mirrors
  the number and disables unselected rows at the limit — unlike `MAX_SKILLS = 32`
  against five shipped skills, which is unreachable, 8 against a 21-file skill is
  one screen away, so the 422 has to be either unreachable or legible. Both:
  `readJson` now flattens FastAPI's validation `detail` ARRAY, which previously
  reached the user as `[object Object]` for every schema limit in the dashboard.
- Selections are deduplicated when resolved. Naming one file twice would inline
  two identical blocks and charge the budget twice, so a duplicated errata could
  trip a limit it comfortably fits inside.
- The stored selection is the CANONICAL form, not the caller's string. Parsing
  strips outer whitespace, so `"rules/a.md"` and `"rules/a.md "` read the same
  file and build the same prompt; storing both verbatim would give one evaluation
  two digests, two idempotency keys, and a duplicate verdict.
- `EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS`, default **60,000**, is a budget across
  all selected references, checked when the request's judge config is resolved.
  60,000 admits the largest single reference (`resources/errata.md`, 38,515 chars)
  plus a second substantial file such as `resources/timing.md` (15,344) — the
  realistic shape of "the judge needs the errata and the timing rules" — while
  refusing a whole-corpus selection outright.

Exceeding the budget is a **400 naming the measured total and the limit**, not a
truncation. `_state_json` truncates game state because a clipped board is still a
board and the alternative is refusing to grade at all; a clipped rulebook is the
exact defect this change exists to fix, and silently handing the judge two thirds
of the errata is worse than telling the operator to select less. The check runs in
`resolve_judge_config`, so it rejects before any target is enqueued — the same
place and the same shape as `UnknownSkillError`.

## 4. Path safety

A `skill_references` entry is caller-supplied text used to open a file, so the
threat is a read of anything outside the skill directory.

### The orchestrator's existing implementation is sound

`SkillRegistry.load_reference_content`
(`services/agent-orchestrator/src/agent_orchestrator/runtime/skills.py:144`)
resolves both sides and requires containment:

```python
skill_path = self._skill_path(skill_name).resolve()
reference_path = (skill_path / reference_name).resolve()
normalized_reference = reference_path.relative_to(skill_path).as_posix()  # ValueError -> 404
... reference_path.suffix != ".md"
 or normalized_reference != reference_name
 or not reference_path.is_file()
 or reference_path.name == "SKILL.md"
```

Checked against each attack:

- **Absolute path** — `Path("/skills/x") / "/etc/passwd"` is `/etc/passwd`;
  `relative_to` raises `ValueError`; refused.
- **`..` traversal out** — resolves outside the skill; `relative_to` raises;
  refused.
- **`..` traversal that lands back inside** (`resources/../resources/faq.md`) —
  contained, but the resolved relative path no longer equals the supplied string,
  so `normalized_reference != reference_name` refuses it. Non-canonical input is
  rejected rather than normalised, which keeps the string in the audit trail equal
  to the file that was read.
- **Symlink escape** — `reference_path.resolve()` follows links *before* the
  containment check, so a link to `/etc/shadow` fails `relative_to`; refused.
  This is the check that matters most and it is present.
- **Skill-name injection** — `_skill_path` goes through `resolve(skill_name)`,
  which is a dict lookup over discovered directory names, so a name is never
  joined onto a path. In `builtin_tools.py` the name must additionally be in the
  session's assigned skills.
- **Directories, non-markdown, `SKILL.md` itself** — refused explicitly.

**No security finding to report against the orchestrator.** Two residual
observations, neither exploitable by a remote caller:

- A TOCTOU window exists between `resolve()` and `read_text()`: a local process
  able to write inside the skill root could swap a path component for a symlink in
  between. A **hardlink** placed inside a skill defeats every path check the same
  way, and by design — a hardlink is indistinguishable from a regular file, so no
  `stat`-based rule can catch it. Both collapse to "someone who can write into
  `SKILL_ROOTS` can put whatever they like there anyway", and neither is reachable
  remotely: skills are `COPY skills ./skills` into the image with
  `SKILL_ROOTS=/app/skills` and no bind mount in `docker-compose.yaml`. Not
  addressed.
- `load_reference_content` raised an uncaught `ValueError` for a reference name
  holding a null byte (`resolve()` raises it, not `OSError`, and the tool handler
  catches only `FileNotFoundError`), so an agent could fail its own whole job with
  `load_skill_reference(skill, "a\0.md")`. Not a disclosure and not a traversal —
  but it is the identical bug this change fixed in eval-service, so it is
  back-ported here rather than left in place next door.
- `list_reference_files` uses `rglob("*.md")` and `relative_to` **without**
  resolving, so it can list an entry that `load_reference_content` then refuses —
  specifically a symlinked `.md` inside the skill, whose resolved relative path no
  longer equals the name it was listed under. That is fail-closed (advertised but
  unreadable), Python's `rglob` does not recurse into symlinked directories by
  default, and no shipped skill contains a symlink, so the case is narrow. Left
  alone deliberately: tightening the listing would change what `load_skill`'s
  "Available references" inventory shows to *agents*, which is outside this
  change.

### What eval-service does

The checks are reproduced — not the code, since the two services do not share a
package — in a single new module,
`services/eval-service/src/eval_service/judge/skill_resources.py`, so every
refusal has one place and one test. Two differences from the orchestrator's
version:

- **`is_symlink()` is rejected explicitly**, on the leaf and on every parent
  component from the skill root down, rather than relying on `resolve()` +
  `relative_to` alone. `resolve()` already blocks the escape; the explicit check
  makes the intent legible, catches it mid-path rather than only at the leaf, and
  removes the component a check-then-read swap would need.
- **Every refusal carries one message**, so which rule was broken — and in
  particular whether the file being reached for exists — cannot be read out of the
  error. A test asserts an existing out-of-bounds target and an absent one refuse
  identically. The specific reason is logged server-side instead: "someone is
  walking paths", "the skills volume is unmounted" and "an operator mistyped a
  filename" are indistinguishable from outside on purpose, and must not be
  indistinguishable from inside.

eval-service deliberately gets **no** reference *listing*. The dashboard already
reads the catalogue from the orchestrator's `GET /skills`, and adding a second,
competing listing in eval-service would be dead code with no caller — exactly the
coupling that already exists for skill *names*, which eval-service also does not
enumerate.

A new file is also the right shape because this change lands on a branch whose
base is about to be rewritten: a self-contained module replays through a rebase
where interleaved edits to a heavily-touched file do not.

## 5. `EVALUATOR_VERSION` stays `eval-2`

The argument for bumping would be "the judge sees something different, so verdicts
are not comparable". It does not apply, because the difference is *addressed by the
config digest*:

- For a judge config with **no** reference selections — every config expressible
  in `eval-2` — the system prompt is byte-identical and
  `ResolvedJudgeConfig.to_json()` omits the new key entirely, so
  `judge_config_digest` and therefore every idempotency key is unchanged. An
  `eval-2` verdict recorded before this change still dedupes against a re-run
  after it. This is pinned by a test asserting the digest of a reference-free
  config against the current value.
- A config **with** references is a new config that no `eval-2` verdict was ever
  produced under. Its digest differs, so its verdict is a distinct history event
  rather than a dedupe against a verdict formed without the references. Nothing
  is silently overwritten and nothing is falsely compared.

Bumping to `eval-3` would instead invalidate the comparability of every existing
`eval-2` verdict — including all of the ones whose prompts this change provably
does not touch — to describe a difference the digest already describes precisely.
That is a strictly worse trade, so the version stays.

The `to_json()` key omission is load-bearing, not a style choice: emitting
`"skill_references": []` unconditionally would change the digest of every config
in existence, so every re-evaluation of every already-graded target would record a
second verdict instead of deduping. It is asserted by a test.

## 6. Discovery

The dashboard's judge panel already lists skills from the agent-orchestrator's
`GET /skills` via `listAvailableSkills()`, and eval-service's default skill root is
documented as the same directory the orchestrator discovers from
(`services/eval-service/src/eval_service/config.py`). So `references: list[str]` is
added to that existing response — `SkillRegistry.list_reference_files` already
computes it — rather than standing up a second, competing catalogue endpoint on
eval-service that the dashboard would have to fetch and reconcile against the
first. One catalogue, one fetch, and the orchestrator's own persona and prompt UIs
get the same data.

## Follow-up: a judge tool loop

Kept out of this change and worth its own issue, because it is a provider-loop
change rather than a prompt change:

- `BifrostJudgeClient` gains a `tools` payload key and returns the assistant
  message rather than its content, so `tool_calls` are visible.
- `Evaluator` gains a bounded tool loop: accumulate assistant/tool messages, cap
  the rounds, and give "round cap reached without a verdict" a terminal target
  state distinct from a parse failure.
- The loop has to interleave with `judge_stream` deltas without corrupting the
  dashboard's delta concatenation, and with the per-attempt retry that currently
  assumes one request per attempt.
- Verdict identity needs re-thinking: either record which skills/references the
  judge actually loaded on the verdict payload and fold that into the idempotency
  key, or accept that the key no longer identifies the evidence.

Worth doing if the judge ever needs to *choose* its evidence — for example a
judge that decides which errata page a specific card interaction requires. It is
not worth doing to deliver rules the operator already knows the judge needs.
