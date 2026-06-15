from __future__ import annotations

import pytest

from game_service.catalog.service import list_prebuilt_sets, search_prebuilt_sets

from .cards_test_support import install_stub_marvel_provider


@pytest.fixture(autouse=True)
def stub_marvel_provider(monkeypatch):
    install_stub_marvel_provider(monkeypatch)


def test_list_prebuilt_sets_returns_records():
    results = list_prebuilt_sets("marvel-champions")
    assert len(results) == 3
    for result in results:
        assert set(result) == {"id", "name", "type"}


def test_search_prebuilt_sets_filters_by_name():
    results = search_prebuilt_sets(name="Valkyrie", provider_name="marvel-champions")
    assert len(results) == 1
    assert results[0]["name"] == "Valkyrie Nemesis"


def test_search_prebuilt_sets_filters_by_type():
    results = search_prebuilt_sets(type="Hero Set", provider_name="marvel-champions")
    assert len(results) == 1
    assert results[0]["type"] == "Hero Set"


def test_search_prebuilt_sets_empty_result():
    results = search_prebuilt_sets(
        name="does-not-exist", provider_name="marvel-champions"
    )
    assert results == []
