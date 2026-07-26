## 1. Serialize offset-assign and publish

- [x] 1.1 Add a per-emitter `asyncio.Lock` to `HistoryEventEmitter`.
- [x] 1.2 In `emit_agent_move`, hold the lock across `next_producer_offset` →
      build envelope → `publish` so the pair is one critical section.
- [x] 1.3 In `emit_user_prompt`, hold the lock across the same offset-assign →
      publish pair.
- [x] 1.4 Preserve best-effort, non-blocking semantics: emission stays detached
      from the tool round and publish failures are still logged and swallowed.

## 2. Tests

- [x] 2.1 Unit test: concurrently fired emissions for one game publish to the
      bus in offset-assignment order even when the bus makes lower offsets
      publish slower (would reorder without the lock).
- [x] 2.2 `./scripts/lint.sh --fix` and `uv run pytest tests/unit` pass.
