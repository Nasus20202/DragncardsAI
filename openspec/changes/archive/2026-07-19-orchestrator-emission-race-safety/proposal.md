# Ordered history emission from the orchestrator

## Why

The orchestrator emits history events (`user_prompt` and `agent_move`) as
detached fire-and-forget asyncio tasks so emission never blocks a prompt job's
tool round. Each emission does two awaits against the history bus: it first
assigns a per-game `producer_offset` (`INCR`), then publishes the envelope
(`XADD` onto the shared `history:ingest` stream). Because the tasks run
concurrently and the event loop can switch between those two awaits, the publish
order can differ from the offset-assignment order:

- Task A assigns offset 1 and yields before publishing.
- Task B assigns offset 2 and publishes offset 2.
- Task A resumes and publishes offset 1 second.

The history-service assigns each game's authoritative, gap-free `seq` by stream
**arrival order** (it uses `producer_offset` only for the idempotency key, not
for ordering). So an out-of-order publish is durably recorded out of order — for
example an `agent_move` recorded before the `user_prompt` that produced it, or
two moves recorded in the wrong order — corrupting the reconstructed timeline
and any restore/evaluation that relies on it. This affects the common case of
several emissions within one job as well as interleaved emissions across
concurrent jobs bound to the same game within one worker process.

## What Changes

- **agent-orchestrator (history emission ordering)** — the offset-assignment and
  publish of a single history event SHALL be a single critical section per
  emitter, so that within a worker process events for a game reach the ingest
  stream in the same order their producer offsets were assigned. Emission stays
  best-effort and non-blocking for the tool round (it remains detached), and a
  publish failure is still swallowed. This is implemented with a per-emitter
  `asyncio.Lock`; no new persistent or in-memory business state is introduced.

## Impact

- Affected specs: `agent-orchestrator` (Agent move/decision event emission —
  ordering guarantee).
- Affected code:
  `services/agent-orchestrator/src/agent_orchestrator/runtime/history_emitter.py`
  (serialize offset-assign + publish under a per-emitter lock in both
  `emit_agent_move` and `emit_user_prompt`).
- No API or schema changes; internal correctness hardening.
