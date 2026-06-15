from __future__ import annotations

import pytest

from .cards_test_support import install_stub_marvel_provider, make_client


@pytest.fixture(autouse=True)
def stub_marvel_provider(monkeypatch):
    install_stub_marvel_provider(monkeypatch)


async def test_list_prebuilt_sets_200():
    async with make_client() as client:
        response = await client.get("/prebuilt-sets/marvel-champions")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["sets"]) == 3
    assert {item["type"] for item in body["sets"]} >= {"Hero Set", "Modular Set"}


async def test_search_prebuilt_sets_by_name():
    async with make_client() as client:
        response = await client.get(
            "/prebuilt-sets/marvel-champions", params={"name": "Valkyrie"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["sets"][0]["name"] == "Valkyrie Nemesis"


async def test_search_prebuilt_sets_empty_result():
    async with make_client() as client:
        response = await client.get(
            "/prebuilt-sets/marvel-champions", params={"name": "missing"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["sets"] == []
