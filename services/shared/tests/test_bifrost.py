from __future__ import annotations

import httpx

from dragncards_common.bifrost import (
    BifrostError,
    extract_error_message,
    gateway_error,
    transport_error,
)


def _response(
    status: int, json_body: object | None = None, text: str = ""
) -> httpx.Response:
    request = httpx.Request("GET", "https://bifrost.local/health")
    if json_body is not None:
        return httpx.Response(status, json=json_body, request=request)
    return httpx.Response(status, text=text, request=request)


def test_bifrost_error_carries_code_and_retryable():
    err = BifrostError("timeout", "boom", retryable=True)
    assert err.code == "timeout"
    assert err.retryable is True
    assert str(err) == "boom"
    assert isinstance(err, RuntimeError)


def test_extract_error_message_prefers_nested_message():
    response = _response(502, {"error": {"message": "gateway exploded"}})
    assert extract_error_message(response) == "gateway exploded"


def test_extract_error_message_falls_back_to_status_on_non_json():
    response = _response(500, text="not json")
    assert extract_error_message(response) == "Bifrost returned HTTP 500"


def test_gateway_error_retryable_for_5xx_and_429():
    assert gateway_error(_response(503, {"message": "down"})).retryable is True
    assert gateway_error(_response(429, {"message": "slow down"})).retryable is True
    assert gateway_error(_response(400, {"message": "bad"})).retryable is False


def test_transport_error_maps_timeout_and_network():
    timeout = transport_error(
        httpx.TimeoutException("t"),
        timeout_message="timed out",
        network_message="net",
    )
    assert timeout.code == "timeout"
    assert timeout.retryable is True

    network = transport_error(
        httpx.ConnectError("c"),
        timeout_message="timed out",
        network_message="net",
    )
    assert network.code == "network_error"
    assert network.retryable is True
