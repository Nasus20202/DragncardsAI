# Tasks

Ordered so each section is independently shippable and a partial run leaves a green
test suite at the end of every task.

## 1. Apply the change

- [x] 1.1 In `services/agent-orchestrator/src/agent_orchestrator/runtime/prompt_run.py`,
      replace the two-summation form at line 1157
      (`estimate = estimate_tokens_for_messages(candidate) + estimate_tokens_for_tools(tools)`)
      with the call to `estimate_request`:
      ```python
      estimate = estimate_request(
          system_prompt="",
          tools=tools,
          replay_messages=candidate,
          context_window_size=context_window_size,
      ).total
      ```
      The `candidate` list built just above (`[*messages]` plus the assistant partial content
      and the continuation instruction) becomes the `replay_messages` argument; `tools` is the
      same variable; `context_window_size` is the same variable.
- [x] 1.2 Leave the imports of `estimate_tokens_for_messages` and `estimate_tokens_for_tools`
      alone. They are still used at `prompt_run.py:497`, `:1289`, `:1395`, and via the
      `compactable_replay` path.

## 2. Verify

- [x] 2.1 `cd services/agent-orchestrator && uv run pytest tests/unit/test_truncated_turn_continuation.py -v` — 11/11 pass.
- [x] 2.2 `cd services/agent-orchestrator && uv run pytest tests/unit/ -v` — 696/696 pass.
- [x] 2.3 `./scripts/lint.sh --fix` — clean across all four services.

## 3. Archive

- [x] 3.1 `openspec archive dra-55-secondary-estimate-request-call-site --yes` to move the
      change into `openspec/changes/archive/2026-08-16-dra-55-secondary-estimate-request-call-site/`.
      Confirm the archive directory exists and contains `proposal.md` and `tasks.md`.
- [x] 3.2 `openspec validate --all` — 17 passed, 1 failed (`spec/typed-game-actions`,
      pre-existing on `main`); this change does not introduce a second.
