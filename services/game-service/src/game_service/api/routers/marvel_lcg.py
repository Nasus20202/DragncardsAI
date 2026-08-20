"""Platform-native marvel-lcg option and catalog routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from game_service.api.deps import SessionIdentifier, get_manager
from game_service.api.models import (
    ChooseGameOptionRequest,
    ChooseGameOptionResponse,
    MarvelLcgDecksResponse,
    MarvelLcgScenariosResponse,
)
from game_service.logic.exceptions import EnumeratedOptionError, SessionError
from game_service.logic.platform import MARVEL_LCG_PLATFORM
from game_service.logic.session_manager import SessionManager
from game_service.marvel_lcg.options import GameOptions

router = APIRouter(tags=["marvel-lcg"])


def _option_driver(session):
    driver = session.driver
    if getattr(driver, "move_surface", None) != "enumerated_options":
        raise EnumeratedOptionError(
            f"Platform '{session.platform}' offers typed actions, not enumerated options"
        )
    return driver


@router.get(
    "/games/{session_id}/options",
    response_model=GameOptions,
    summary="List the enumerated legal options for a seat",
    operation_id="list_game_options",
)
async def list_game_options(
    session_id: SessionIdentifier,
    player_n: str = Query("player1", pattern=r"^player[1-4]$"),
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        driver = _option_driver(session)
        options = await driver.list_options(player_n)
        options.session_id = session.session_id
        return options


@router.post(
    "/games/{session_id}/options/choose",
    response_model=ChooseGameOptionResponse,
    summary="Choose one enumerated legal option",
    operation_id="choose_game_option",
)
async def choose_game_option(
    session_id: SessionIdentifier,
    body: ChooseGameOptionRequest,
    manager: SessionManager = Depends(get_manager),
):
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        driver = _option_driver(session)
        result = await driver.choose_option(
            body.player_n,
            option_id=body.option_id,
            targets=body.targets,
            resources=body.resources,
            decline=body.decline,
            prompt_id=body.prompt_id,
            prompt_version=body.prompt_version,
        )
        return ChooseGameOptionResponse(session_id=session.session_id, **result)


@router.get(
    "/marvel-lcg/scenarios",
    response_model=MarvelLcgScenariosResponse,
    summary="List vendored marvel-lcg scenarios",
    operation_id="list_marvel_lcg_scenarios",
)
async def list_marvel_lcg_scenarios(manager: SessionManager = Depends(get_manager)):
    driver = manager.platform_driver(MARVEL_LCG_PLATFORM)
    if not hasattr(driver, "list_scenarios"):
        raise SessionError("marvel-lcg catalog is not configured")
    await driver.authenticate()
    return MarvelLcgScenariosResponse(scenarios=await driver.list_scenarios())


@router.get(
    "/marvel-lcg/decks",
    response_model=MarvelLcgDecksResponse,
    summary="List vendored marvel-lcg starter decks",
    operation_id="list_marvel_lcg_decks",
)
async def list_marvel_lcg_decks(manager: SessionManager = Depends(get_manager)):
    driver = manager.platform_driver(MARVEL_LCG_PLATFORM)
    if not hasattr(driver, "list_starter_deck"):
        raise SessionError("marvel-lcg catalog is not configured")
    await driver.authenticate()
    return MarvelLcgDecksResponse(decks=await driver.list_starter_deck())
