## 1. Validate the restore request

- [x] 1.1 Add a bounded message-count limit, a bounded serialized-size limit, and
      an allowed-role set as module constants in `schemas/sessions.py`.
- [x] 1.2 Add a `field_validator` on `SessionRestoreRequest.conversation_context`
      that rejects: too many messages, a non-object message, a message whose
      `role` is missing/non-string/outside the allowed set, and an oversized
      serialized payload.
- [x] 1.3 Length-bound `game_id` on `SessionRestoreRequest` consistently with the
      history-service `game_id` contract.

## 2. Tests

- [x] 2.1 Unit test: a message with no `role` is rejected with 422.
- [x] 2.2 Unit test: a message with an unknown `role` is rejected with 422.
- [x] 2.3 Unit test: exceeding the message-count limit is rejected with 422.
- [x] 2.4 Unit test: exceeding the serialized-size limit is rejected with 422.
- [x] 2.5 Existing well-formed restore tests still pass;
      `./scripts/lint.sh --fix` and `uv run pytest tests/unit` pass.
