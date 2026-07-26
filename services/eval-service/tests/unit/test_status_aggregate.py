from __future__ import annotations

from eval_service.runtime.status import request_status


class _T:
    """Minimal stand-in carrying just the ``status`` field of a target row."""

    def __init__(self, status: str):
        self.status = status


def _agg(*statuses: str) -> str:
    return request_status([_T(s) for s in statuses])  # type: ignore[arg-type]


def test_pending_when_any_non_terminal():
    assert _agg("completed", "running") == "pending"
    assert _agg("pending", "cancelled") == "pending"


def test_completed_when_all_completed():
    assert _agg("completed", "completed") == "completed"


def test_failed_when_none_completed_and_no_cancel():
    assert _agg("skipped", "failed") == "failed"


def test_cancelled_when_any_cancelled_and_none_failed():
    assert _agg("cancelled", "skipped") == "cancelled"
    assert _agg("cancelled", "cancelled") == "cancelled"
    # Per the contract aggregate rule, ``cancelled`` (any cancelled & none
    # failed) takes precedence over ``partial`` even alongside completed ones.
    assert _agg("completed", "cancelled") == "cancelled"


def test_partial_when_mix_of_completed_and_skipped():
    assert _agg("completed", "skipped") == "partial"


def test_failed_takes_precedence_over_cancelled_when_no_completed():
    # any cancelled but ALSO a failure (and none completed) -> failed.
    assert _agg("cancelled", "failed") == "failed"


def test_empty_is_completed():
    assert _agg() == "completed"
