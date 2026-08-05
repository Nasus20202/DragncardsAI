# Make the auto-compaction trigger and the context widget report one number

## Why

The auto-compaction trigger and the dashboard's context widget measure
different things, so they report different numbers for the same session. The
trigger fires against a figure the user never sees; the widget reassures with a
figure the trigger ignores.

This is option **(B)** of DRA-12's context-management proposal. The owner
approved (A) and (C) and withheld sign-off on (B), which was split out as
DRA-33. The design was written at the time and deliberately kept in
`design.md` rather than in a spec delta, because a delta is applied to the main
spec on archive and would have written unimplemented behaviour into it. This
change implements that design, with two argued deviations recorded in
`design.md`.

### What each side measured, and by how much they differed

Measured against the running deployment, through its own
`GET /sessions/{id}/context`, over every session with a model configured. The
window is 128,000 tokens throughout; the session carries 36 MCP tool
definitions.

| Session | Trigger saw (replay only) | Widget showed (system prompt + replay + MCP tools) | Trigger's shortfall |
| --- | --- | --- | --- |
| `8d7c8d5a` | 0 (0.000) | 12,779 (0.100) | 12,779 |
| `e8fb8860` | 5,403 (0.042) | 18,182 (0.142) | 12,779 |
| `1026e4d7` | 6,008 (0.047) | 18,787 (0.147) | 12,779 |
| `408540a0` | 9,279 (0.073) | 22,058 (0.172) | 12,779 |
| `e5dce782` | 12,258 (0.096) | 25,037 (0.196) | 12,779 |
| `75bfcf05` | 43,617 (0.341) | 56,396 (0.441) | 12,779 |
| `dbe97e1b` | 56,499 (0.441) | 69,278 (0.541) | 12,779 |
| `aa079410` | 152,014 (1.188) | 164,793 (1.000, clamped) | 12,779 |

The divergence is a constant **12,779 tokens — 9.98% of the window** — on every
session: the system prompt (1,588) plus the MCP tool definitions (11,191).
Every ratio the trigger computed was 0.0998 lower than the one the widget
displayed at the same moment.

### Neither side measured the whole request

The widget was closer but not correct, and the trigger was missing more than
the widget's total:

- **Built-in tool definitions: 1,071 tokens** for a top-level job (five tools:
  `load_skill`, `load_skill_reference`, `spawn_subagent`, `wait_for_subagent`,
  `ask_user`), 205 for a subagent, measured by building the registry. The
  widget costed the MCP half only, so the session above offers the model 41
  tools and had 36 of them counted.
- **The current turn's user message as rendered.** DRA-15 lets a prompt inline
  a skill into its own turn. The five runtime skills render to 2,376–7,081
  tokens each, and `MAX_INLINE_SKILLS = 4`: the largest four together render to
  **16,301 tokens** against a bare prompt's 4. The trigger ran *before* that
  message was rendered, so it never saw it at all.
- **The persona catalogue in the system prompt.** The widget built the prompt
  without `personas=`, which the worker always passes. The deployment has no
  personas configured today, so this contributes 0 there — but it is a silent
  under-count the moment one exists.

So on a top-level turn the trigger's blind spot ran from **13,850 tokens
(10.8% of the window)** with no skill inlined to **30,151 tokens (23.6%)** with
four.

### Why that matters rather than merely being untidy

`CONTEXT_COMPACTION_THRESHOLD` is `0.8`, so on a 128,000-token window the old
trigger deferred compaction until the replay alone reached 102,400 tokens. At
that moment the request actually being assembled was 116,250 tokens, and with
four skills inlined **132,551 tokens — 4,551 over the window**. The trigger
whose whole purpose is to keep a request inside the window could hand the
provider one it must reject. That is the `context_length_exceeded` failure
DRA-12's (A4) converted from a failed turn into a degraded one; (B) is what
stops it being reached.

## What Changes

- **One function is now the source of the number.** A new
  `runtime/context_estimate.py` holds `estimate_request`, the only place
  context components are added together. The trigger and the context metadata
  endpoint both read their figure off it.
- **The trigger measures the request it is about to send**: system prompt, all
  tool definitions (built-in and MCP), the replay, and the current turn's user
  message as rendered. `render_prompt_with_inline_skills` is hoisted above the
  auto-compaction call so the inlined skill content is in scope; the prompt
  event and the `skill_loaded` announcements stay where they were, so the
  transcript's ordering is unchanged.
- **The widget's estimate gains the built-in tool definitions and the persona
  catalogue**, so the two sides agree on all three components they can both
  know. The widget's appearance is untouched — no new row, no restyling. Its
  breakdown keeps its three fields.
- **A guard stops the trigger compacting what it cannot shrink.** Once fixed
  costs count, a session can exceed the threshold with an empty replay.
  Compaction rewrites only the replay, so the trigger now skips when the replay
  is smaller than the summary that would replace it, and logs that the
  threshold was reached by fixed request cost rather than by history. New
  `CONTEXT_COMPACTION_MIN_REPLAY_TOKENS` (int, default `4000`) is the floor
  used before a session has a summary to measure against.
- **The INFO log line reports the component estimates**, which is what makes
  agreement with the widget observable on a real session.
- **`CONTEXT_COMPACTION_THRESHOLD` stays at `0.8`.** Correcting what is
  measured already moves the effective trigger earlier; moving the threshold in
  the same change would make the result unevaluable.
- Two dead `F401` imports are removed from `runtime/session_transcript.py`, and
  three more from `tests/unit/test_auto_compaction.py`, both files this change
  edits. `scripts/lint.sh` runs only `black` for Python and never `ruff check`,
  which is why they survived; adding `ruff` to the lint script is a separate
  issue and is not attempted here.

## Impact

- Affected specs: `agent-orchestrator` — the "Auto-compaction at job start" and
  "Context metadata endpoint" requirements.
- Affected code: `services/agent-orchestrator/src/agent_orchestrator/` —
  `runtime/context_estimate.py` (new), `runtime/prompt_run.py`,
  `runtime/session_transcript.py`, `runtime/builtin_tools.py`,
  `runtime/worker.py`, `api/tool_catalog.py`, `api/routers/context.py`,
  `repositories/context.py`, `config.py`.
- No dashboard code changes. The widget renders what the endpoint reports and
  the endpoint's response shape is unchanged.
- No database change: no new table, column or migration. The floor is
  configuration, the summary size is read from the existing
  `CompactionRecord.summary_text`, and nothing is held in memory across
  requests.
- Sessions will compact **earlier in wall-clock terms** than before, by roughly
  the fixed cost — about 13,850 tokens of replay on this deployment, more when
  a prompt inlines skills. That is the intended correction, not a side effect.
- `GET /sessions/{id}/context` will report a larger `tokens_used` for every
  session than it did before, by the built-in tool definitions (1,071 tokens
  here). The widget will show a slightly fuller bar for an unchanged session;
  the bar is now telling the truth.
