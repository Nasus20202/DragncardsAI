"""Failsafes that end a subagent job which would otherwise hang forever.

The worker loop only ends a job when the model produces a terminal state or the
tool-round limit is hit, so a subagent whose provider call never returns, whose
model keeps failing with the same transport error, or whose model keeps
returning empty responses stays ``running`` indefinitely (DRA-51). One
:class:`SubagentFailsafe` per subagent run owns the three checks that stop
that:

* **timeout** — an absolute deadline from the start of the run. If no terminal
  event is produced within it, the run fails with ``subagent_timeout``. The
  deadline bounds the model call itself, so a provider that hangs is cancelled
  when the budget is spent rather than holding the worker.
* **error loop** — a model-call failure is counted by its error code. The same
  code on three consecutive calls is a repeating failure, not a transient
  blip, and fails the run with ``subagent_error_loop``.
* **no progress** — an empty response (no tool calls, no content) is not a
  completion for a subagent. Three consecutive empties fail the run with
  ``subagent_no_progress``; any content or tool call resets the streak, because
  work happening is evidence the model is not stuck.

All three raise :class:`SubagentFailsafeError`, which the worker's failure
handling records as a normal job ``failure`` carrying the error code, and the
child monitor reports on the parent job as a ``subagent_failed`` event whose
``reason`` is the failsafe's own reason rather than a generic ``failed``.

The checks are scoped to subagent runs (``parent_job_id`` set): top-level jobs
never construct a :class:`SubagentFailsafe`, so their behaviour is unchanged.

One instance belongs to one run and dies with it. Nothing here is shared state
the service would want back, so none of it touches PostgreSQL or Valkey.
"""

from __future__ import annotations

import time
from typing import Any

# The error codes a failsafe marks a job failed with. These are also what the
# child monitor maps onto a parent-side `subagent_failed` reason.
SUBAGENT_TIMEOUT_ERROR_CODE = "subagent_timeout"
SUBAGENT_ERROR_LOOP_ERROR_CODE = "subagent_error_loop"
SUBAGENT_NO_PROGRESS_ERROR_CODE = "subagent_no_progress"

# The `reason` a parent-side `subagent_failed` event carries for each failsafe,
# so the session timeline says *why* rather than only that the child failed.
FAILSAFE_REASON_BY_ERROR_CODE: dict[str, str] = {
    SUBAGENT_TIMEOUT_ERROR_CODE: "timeout",
    SUBAGENT_ERROR_LOOP_ERROR_CODE: "error_loop",
    SUBAGENT_NO_PROGRESS_ERROR_CODE: "no_progress",
}


class SubagentFailsafeError(Exception):
    """Raised when a failsafe ends a subagent's run.

    ``error_code`` is what the job is marked failed with, ``reason`` is what
    the parent-side ``subagent_failed`` event carries, and ``message`` names
    what was observed so the failure is diagnosable from the event alone.
    """

    def __init__(self, error_code: str, reason: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.reason = reason
        self.message = message

    def as_failure(self) -> dict[str, Any]:
        """The payload a job failure event carries for this failsafe.

        ``retryable`` is false by design: a failsafe is a definitive stop, not
        a transient blip, so ``mark_job_failed`` never re-queues the child.
        """
        return {
            "code": self.error_code,
            "message": self.message,
            "retryable": False,
        }


class SubagentFailsafe:
    """Tracks the three failsafes for one subagent job run."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_consecutive_errors: int = 3,
        max_empty_responses: int = 3,
    ):
        self._deadline = time.monotonic() + timeout_seconds
        self._max_consecutive_errors = max_consecutive_errors
        self._max_empty_responses = max_empty_responses
        self._last_error_code: str | None = None
        self._last_error_message: str | None = None
        self._consecutive_errors = 0
        self._consecutive_empty = 0

    # -- timeout -----------------------------------------------------------

    def remaining_seconds(self) -> float:
        """How much of the run's budget is left, for bounding one model call."""
        return max(self._deadline - time.monotonic(), 0.0)

    def check_timeout(self) -> None:
        """Fail the run when it has produced no terminal event within the budget.

        Called at the top of every tool round and when the bounded model call
        itself times out, so neither a chatty round loop nor a hanging provider
        can outlive the deadline.
        """
        if time.monotonic() >= self._deadline:
            raise SubagentFailsafeError(
                SUBAGENT_TIMEOUT_ERROR_CODE,
                reason="timeout",
                message=(
                    "Subagent produced no terminal event within the configured "
                    "timeout budget"
                ),
            )

    # -- error loop --------------------------------------------------------

    def note_model_error(self, error_code: str, message: str | None = None) -> None:
        """Count one model-call failure; fail after three identical consecutive ones.

        A transport failure repeating is exactly the "subagent crashes without
        error" symptom this exists to bound: the call keeps raising the same
        code, and without the counter the run would either fail on the first
        blip or never end. A different code resets the streak, because a
        changing failure is a progression rather than a loop.
        """
        if error_code == self._last_error_code:
            self._consecutive_errors += 1
            self._last_error_message = message or self._last_error_message
        else:
            self._last_error_code = error_code
            self._last_error_message = message
            self._consecutive_errors = 1
        if self._consecutive_errors >= self._max_consecutive_errors:
            detail = (
                f" ({self._last_error_message})" if self._last_error_message else ""
            )
            raise SubagentFailsafeError(
                SUBAGENT_ERROR_LOOP_ERROR_CODE,
                reason="error_loop",
                message=(
                    f"Subagent failed with the same error ({error_code}) on "
                    f"{self._consecutive_errors} consecutive model calls{detail}"
                ),
            )

    # -- no progress -------------------------------------------------------

    @staticmethod
    def _is_empty(response: Any) -> bool:
        """True when a response carries neither tool calls nor content."""
        return not response.tool_calls and not (response.content or "").strip()

    def note_response(self, response: Any) -> None:
        """Count one model response; fail after three consecutive empty ones.

        Called for every response of the run. Content or tool calls reset both
        the empty streak and the error streak: work happening is evidence the
        model is not stuck.
        """
        self._last_error_code = None
        self._last_error_message = None
        self._consecutive_errors = 0
        if not self._is_empty(response):
            self._consecutive_empty = 0
            return
        self._consecutive_empty += 1
        if self._consecutive_empty >= self._max_empty_responses:
            raise SubagentFailsafeError(
                SUBAGENT_NO_PROGRESS_ERROR_CODE,
                reason="no_progress",
                message=(
                    f"Subagent returned an empty response (no tool calls, no "
                    f"content) on {self._consecutive_empty} consecutive model calls"
                ),
            )

    def is_empty(self, response: Any) -> bool:
        """True when the response is empty and should not complete the run.

        The worker calls this where it would otherwise complete the job, so a
        subagent's empty answer loops back to the model instead — which is what
        lets the streak above reach its cap.
        """
        return self._is_empty(response)
