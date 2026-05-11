## Context

The agent-orchestrator runs LLM jobs for each user prompt. Today, each job builds a fresh `messages` list from only the current system prompt and user input — prior job events are never replayed. For a turn-based game like Marvel Champions, this means the agent is amnesiac across turns: it cannot reason about prior actions, card states, or decisions.

The raw material for multi-turn memory already exists: `JobEvent` rows are persisted in the DB for every job (model output, tool calls, tool results, completion). What's missing is the worker reading them back at job start.

Additionally, the LLM response `usage` field (containing token counts) is available in the `raw` response dict but is silently dropped today. No token tracking exists anywhere.

## Goals / Non-Goals

**Goals:**
- Replay prior job events into new job message history when `multi_turn_memory` is enabled on the session
- Extract and persist token usage from LLM responses per job
- Introduce `CompactionRecord`: a persisted summary that acts as a checkpoint, replacing raw event replay up to that point
- Manual compaction: `POST /sessions/{id}/compact` triggers summarization and creates a `CompactionRecord`
- Auto-compaction: fires before job start when estimated token usage exceeds threshold
- `GET /sessions/{id}/context` endpoint returning context health metadata
- Dashboard context health indicator and Compact button

**Non-Goals:**
- Deleting raw `JobEvent` rows after compaction (audit trail preserved)
- Per-session threshold configuration (env var only)
- Multi-model tokenizer support
- Modifying DragnCards backend

## Decisions

### D1: Multi-turn memory is opt-in per session

**Decision**: `AgentSession` gets a `multi_turn_memory` boolean flag (default `true`). When `false`, job worker behaves exactly as today — fresh messages list.

**Alternatives considered**:
- *Global setting*: Loses per-session flexibility. Some sessions are exploratory one-shots.
- *Per-prompt flag*: Too granular, adds API complexity.

**Rationale**: Session-level is the natural scope. Same pattern as `model_config` and skill assignments.

---

### D2: Replay source — JobEvent rows, structured back into messages

**Decision**: At job start (when `multi_turn_memory` is enabled), the worker queries all `JobEvent` rows for the session's prior jobs in order, reconstructing the message sequence: user prompt → assistant output → tool calls/results → next user prompt → etc.

If a `CompactionRecord` exists, only jobs **after** the compaction checkpoint are replayed; the summary is injected as a system message first.

**Alternatives considered**:
- *Store raw messages list per job*: Duplicates data; JobEvents already capture everything needed.
- *Replay only last N jobs*: Arbitrary cutoff; compaction is the right mechanism for history management.

**Rationale**: JobEvents are already the source of truth. Compaction is the explicit control surface for history depth.

---

### D3: Token tracking — extract from raw LLM response, persist on Job

**Decision**: After each LLM call, extract `usage.total_tokens` from `ChatResponse.raw`. Store as `tokens_used` on the `Job` row. When `usage` is absent, estimate via tiktoken and log a WARNING.

**Alternatives considered**:
- *In-memory tracker on session object*: Lost on restart; doesn't survive across jobs.
- *Compute from message list length*: Inaccurate, model-dependent.

**Rationale**: Persisting on `Job` gives a queryable history of token usage per job, useful for context metadata and future analytics. `ChatResponse.raw` already has the data.

---

### D4: CompactionRecord — new DB table, not a special JobEvent type

**Decision**: New `CompactionRecord` table with: `id`, `session_id`, `summary_text`, `covers_up_to_job_id`, `tokens_used` (of the summary), `created_at`.

**Alternatives considered**:
- *Special JobEvent type*: Awkward semantics; compaction isn't a job event.
- *Store in session metadata_json*: Unbounded blob, only one record, not queryable.

**Rationale**: Clean separation. The compaction record is a checkpoint concept, not a job event.

---

### D5: Compaction triggers — both manual and auto

**Decision**: 
- **Manual**: `POST /sessions/{id}/compact` available anytime. Creates a `CompactionRecord`, raw events kept for audit.
- **Auto**: Fires at job start (before worker builds messages) when sum of `tokens_used` across jobs since last compaction exceeds `CONTEXT_COMPACTION_THRESHOLD` ratio of `CONTEXT_WINDOW_SIZE`. Logs INFO with pre-compaction ratio.

Threshold: `CONTEXT_COMPACTION_THRESHOLD` env var (float, default `0.8`).  
Window size: `CONTEXT_WINDOW_SIZE` env var (int, default `128000`).

**Alternatives considered**:
- *Manual only*: User won't always know when to compact; long game runs degrade silently.
- *Auto only*: Removes user agency; less predictable.
- *Fire auto after job completion (async)*: Pre-job is safer — you never start a job already over the limit.

**Rationale**: Manual for control, auto for safety. Both create the same `CompactionRecord` via the same compaction logic.

---

### D6: Dashboard — Compact button + context health indicator, not a command bar

**Decision**: A dedicated context health widget in the dashboard showing a token usage progress bar, percentage, compaction count, and last-compacted timestamp. A "Compact" button within the widget triggers `POST /sessions/{id}/compact`.

**Alternatives considered**:
- *`/compact` command in a command input field*: Less discoverable, more typing, command bar adds complexity for one action.

**Rationale**: A button next to the indicator is the most direct UX. The indicator makes the button's purpose self-evident.

## Risks / Trade-offs

- **[Risk] Replaying all prior job events inflates message list size significantly** → Mitigation: Auto-compaction threshold keeps this bounded. Manual compact available before threshold if needed.
- **[Risk] Summarization LLM call loses game-critical details** → Mitigation: Compaction prompt explicitly instructs preservation of: hero HP, threat levels, villain phase, encounter deck status, all cards in play. Tested against real game transcripts before shipping.
- **[Risk] `usage` field absent from Bifrost gateway response** → Mitigation: tiktoken fallback; WARNING logged. Token estimates will be slightly inaccurate but still directionally correct.
- **[Risk] Auto-compaction adds latency at job start** → Mitigation: Only fires when threshold exceeded; compaction is a single LLM call before the job's actual work begins. Acceptable tradeoff for correctness.
- **[Risk] Context window size varies by model** → Mitigation: `CONTEXT_WINDOW_SIZE` env var; no dynamic detection in v1.
