import asyncio

import pytest

from agent_orchestrator.runtime.session_dispatch_lock import SessionDispatchLock


class FakeRespConnection:
    def __init__(self) -> None:
        self.value: tuple[str, str] | None = None
        self.calls: list[tuple[object, ...]] = []

    async def execute(self, *parts: object):
        self.calls.append(parts)
        if parts[0] == "SET":
            if self.value is not None:
                return None
            self.value = (str(parts[1]), str(parts[2]))
            return "OK"
        if parts[0] == "EVAL":
            key = str(parts[3])
            token = str(parts[4])
            if self.value == (key, token):
                self.value = None
                return 1
            return 0
        raise AssertionError(f"unexpected command: {parts[0]}")


@pytest.mark.asyncio
async def test_session_lock_serializes_contending_tasks():
    connection = FakeRespConnection()
    lock = SessionDispatchLock(connection)  # type: ignore[arg-type]
    entered: list[str] = []
    second_entered = asyncio.Event()

    async def first():
        async with lock.for_session("session-1"):
            entered.append("first")
            await asyncio.sleep(0.02)

    async def second():
        async with lock.for_session("session-1"):
            entered.append("second")
            second_entered.set()

    first_task = asyncio.create_task(first())
    await asyncio.sleep(0)
    second_task = asyncio.create_task(second())
    await asyncio.sleep(0.01)
    assert entered == ["first"]
    assert not second_entered.is_set()

    await asyncio.gather(first_task, second_task)
    assert entered == ["first", "second"]
    assert connection.value is None


@pytest.mark.asyncio
async def test_session_lock_does_not_release_another_owner():
    connection = FakeRespConnection()
    lock = SessionDispatchLock(connection)  # type: ignore[arg-type]

    async with lock.for_session("session-1"):
        key, token = connection.value or ("", "")
        connection.value = (key, "different-owner")

    assert connection.value == (key, "different-owner")
    assert connection.calls[-1][0] == "EVAL"
