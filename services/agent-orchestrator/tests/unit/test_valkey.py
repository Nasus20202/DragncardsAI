from __future__ import annotations

from agent_orchestrator.storage.valkey import RespConnection


def test_from_url_on_subclass_injects_default_tracer():
    # The inherited ``from_url`` forwards ``tracer=`` into the subclass __init__;
    # without accepting it this would raise TypeError.
    conn = RespConnection.from_url("valkey://cache-host:6390")
    assert conn._host == "cache-host"
    assert conn._port == 6390
    assert conn._tracer is not None  # module tracer wired in by default


def test_from_url_on_subclass_respects_explicit_tracer():
    sentinel = object()
    conn = RespConnection.from_url("valkey://cache-host:6390", tracer=sentinel)
    assert conn._tracer is sentinel
