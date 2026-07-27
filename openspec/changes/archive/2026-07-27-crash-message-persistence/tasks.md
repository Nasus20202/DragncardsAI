## 1. Guard the whole prompt run

- [x] 1.1 Move the run prologue (cancellation check, job load, model-config
      check) inside the `try` in `PromptRunService.run` so a crash there is
      recorded instead of escaping.
- [x] 1.2 Seed `full_job = job` before the `try` so failure handling has a job
      to record against even when the job reload is what crashed.
- [x] 1.3 Remove the dead `get_model_context_length` / `context_window_size`
      computation in `run` — unused, and an unguarded network call.
- [x] 1.4 Replace the hand-picked `except (McpClientError, RuntimeError,
      ValueError, InvalidToolInvocationError)` with `except Exception`, keeping
      the dedicated `BifrostError` branch and leaving `asyncio.CancelledError`
      uncaught.

## 2. Last-resort terminal status in the worker

- [x] 2.1 Wrap `WorkerService._run_job` so an exception escaping the prompt run
      is logged rather than silently lost in a detached task.
- [x] 2.2 In that guard, mark the job `failed` with `error_code =
      "worker_crash"`, and log if even that fails.

## 3. Tests

- [x] 3.1 Unit test: a `TimeoutError` from `chat_completion` marks the job
      `failed`, writes a `failure` event, and the prompt plus the synthetic
      "previous turn failed" note appear in the next run's replayed context.
- [x] 3.2 Same test parameterised over an `ExceptionGroup` crash.
- [x] 3.3 Unit test: a crash in the run prologue (before the first model call)
      still reaches `failed` and keeps the prompt in the replayed context.
- [x] 3.4 Unit test: when `PromptRunService.run` itself raises, the worker marks
      the job `failed` with `error_code = "worker_crash"` and the prompt is
      still replayed.
- [x] 3.5 `./scripts/lint.sh --fix` and `./scripts/test.sh unit` pass.
