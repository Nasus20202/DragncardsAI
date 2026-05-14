from __future__ import annotations

import httpx
import pytest


@pytest.mark.asyncio
async def test_job_endpoints_return_404_for_missing_job(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        job_response = await client.get("/jobs/missing-job")
        status_response = await client.get("/jobs/missing-job/status")
        events_response = await client.get("/jobs/missing-job/events")
        stream_response = await client.get("/jobs/missing-job/events/stream")
        cancel_response = await client.post("/jobs/missing-job/cancel")

    assert job_response.status_code == 404
    assert status_response.status_code == 404
    assert events_response.status_code == 404
    assert stream_response.status_code == 404
    assert cancel_response.status_code == 404
