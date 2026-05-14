from __future__ import annotations

from agent_orchestrator.runtime.memory import _reconstruct_job_messages

from .memory_test_support import make_mock_job_with_tool_events


def test_reconstruct_job_messages_with_tool_calls():
    mock_job = make_mock_job_with_tool_events()

    messages = _reconstruct_job_messages(mock_job)

    assert messages[0] == {"role": "user", "content": "do a thing"}
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Using tool..."
    assert len(messages[1]["tool_calls"]) == 1
    assert messages[1]["tool_calls"][0]["id"] == "tc1"
    assert messages[2]["role"] == "tool"
    assert messages[2]["tool_call_id"] == "tc1"
