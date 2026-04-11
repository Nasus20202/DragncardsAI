"""
DragnCards HTTP client helpers.

These functions encapsulate the three HTTP calls required to bootstrap
a new game session: authenticate, look up the user ID, and create a room.
They are intentionally stateless — each call creates a short-lived httpx
client and closes it on exit.
"""

from __future__ import annotations

import httpx


async def get_auth_token(http_url: str, email: str, password: str) -> str:
    """Authenticate with DragnCards and return a Pow session token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{http_url}/api/v1/session",
            json={"user": {"email": email, "password": password}},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()["data"]["token"]


async def get_user_id(http_url: str, auth_token: str) -> int:
    """Return the numeric user ID for the authenticated user."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{http_url}/api/v1/profile",
            headers={"authorization": auth_token},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        # Profile endpoint returns {"user_profile": {...}} not {"data": {...}}
        if "user_profile" in data:
            return data["user_profile"]["id"]
        return data["data"]["id"]


async def create_room(
    http_url: str,
    auth_token: str,
    user_id: int,
    plugin_id: int,
    plugin_version: int,
    plugin_name: str,
) -> dict:
    """Create a DragnCards game room and return the room dict."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{http_url}/api/v1/games",
            headers={"authorization": auth_token},
            json={
                "room": {"user": user_id, "privacy_type": "public"},
                "game_options": {
                    "plugin_id": plugin_id,
                    "plugin_version": plugin_version,
                    "plugin_name": plugin_name,
                    "replay_uuid": None,
                    "external_data": None,
                    "ringsdb_info": None,
                },
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["success"]["room"]
