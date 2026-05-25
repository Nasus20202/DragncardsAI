from __future__ import annotations

import pytest

from game_service.catalog.providers.marvel_champions import prebuilt_decks

from .cards_test_support import install_stub_marvel_provider


@pytest.fixture(autouse=True)
def stub_marvel_provider(monkeypatch):
    install_stub_marvel_provider(monkeypatch)


def test_load_prebuilt_decks_returns_catalog():
    decks = prebuilt_decks.load_prebuilt_decks()
    assert "set-001" in decks
    assert decks["set-001"]["deck_id"] == "Spider-Verse (Hero)"
    assert decks["set-001"]["label"] == "Spider-Verse"


def test_get_prebuilt_deck_by_id_returns_deck():
    deck = prebuilt_decks.get_prebuilt_deck_by_id("set-001")
    assert deck is not None
    assert deck["label"] == "Spider-Verse"


def test_get_prebuilt_deck_by_id_missing_returns_none():
    assert prebuilt_decks.get_prebuilt_deck_by_id("missing") is None
