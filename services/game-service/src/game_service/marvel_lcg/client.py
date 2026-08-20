"""Strict HTTP transport for the vendored marvel-lcg web API.

The engine deliberately answers missing-auth and stale-version requests with a
human HTML page and HTTP 200.  This client validates the response before parsing
it, and keeps the tiny allow-list here so a caller can never turn a game route
into a generic proxy for the engine.
"""

from __future__ import annotations

import hashlib
import gzip
import json
import re
from dataclasses import dataclass, field
from http.cookiejar import Cookie, CookieJar, DefaultCookiePolicy
from typing import Any, Iterable, Mapping
from urllib.parse import quote, urlsplit

import httpx

from game_service.logic.exceptions import SessionError
from game_service.telemetry import get_tracer

tracer = get_tracer(__name__)


class MarvelLcgError(SessionError):
    """Base error for a marvel-lcg transport or protocol failure."""


class MarvelLcgAuthenticationError(MarvelLcgError):
    """The engine returned its authentication or cache-clearing page."""


class MarvelLcgContentTypeError(MarvelLcgError):
    """The engine returned a body with an unexpected media type."""


class MarvelLcgHttpError(MarvelLcgError):
    """A non-success HTTP response from the engine."""

    def __init__(self, status_code: int, path: str, detail: str = "") -> None:
        self.status_code = status_code
        self.path = path
        # Upstream response bodies can contain the submitted game descriptor or
        # other engine-internal data.  Keep the compatibility attribute but never
        # copy that body into an exception message or a log record.
        self.detail = ""
        super().__init__(f"marvel-lcg {path} returned HTTP {status_code}")


class UnsafeCookiePolicy(DefaultCookiePolicy):
    """Cookie policy that accepts and returns cookies for IP-address hosts.

    ``http.cookiejar`` is intentionally conservative around a bare IP.  The
    engine is commonly addressed by a Docker service name or local IP, and its
    version gate is a real cookie rather than a header.  Relax only domain
    matching; path and expiry handling remain delegated to the standard jar.
    """

    def set_ok(self, cookie: Cookie, request: Any) -> bool:  # noqa: N802
        return True

    def return_ok(self, cookie: Cookie, request: Any) -> bool:  # noqa: N802
        return True


class UnsafeCookieJar(CookieJar):
    """CookieJar suitable for the engine's IP-address deployment mode."""

    def __init__(self) -> None:
        super().__init__(policy=UnsafeCookiePolicy())


@dataclass(frozen=True)
class NewGameDescriptor:
    """The subset of the engine's new-game descriptor used by this service."""

    campaign_json: str
    encounter_set_names: list[str]
    hero_json: list[str]
    seed: int = 0
    timeout: float = 0
    challenges: list[str] | None = None
    rules: list[str] = field(default_factory=lambda: ["v18_all"])
    campaign_log: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.campaign_json, str):
            raise TypeError("campaign_json must contain document content, not a path")
        if not self.hero_json or not all(
            isinstance(item, str) for item in self.hero_json
        ):
            raise TypeError("hero_json must be a non-empty list of document contents")
        for field_name, document in (
            ("campaign_json", self.campaign_json),
            *[("hero_json", item) for item in self.hero_json],
        ):
            try:
                json.loads(document)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{field_name} must contain stringified JSON document content"
                ) from exc

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "campaign_json": self.campaign_json,
            "encounter_set_names": self.encounter_set_names,
            "hero_json": self.hero_json,
            "seed": self.seed,
            "timeout": self.timeout,
            "challenges": self.challenges or [],
            "rules": list(self.rules),
            "campaign_log": self.campaign_log or {},
        }
        return result


_ALLOWED_PATHS = frozenset(
    {
        "/authenticate",
        "/get_version",
        "/list_scenarios",
        "/list_starter_deck",
        "/get_scenario_json",
        "/get_hero_json",
        "/new",
        "/get_world",
        "/get_ask",
        "/post",
        "/client_updated",
    }
)
_SAFE_DOCUMENT_PATH = re.compile(r"^[^/?#\\]+(?:/[^/?#\\]+)*$")


def _content_type(response: httpx.Response) -> str:
    return response.headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _is_json_content_type(value: str) -> bool:
    return value in {
        "application/json",
        "text/json",
        "application/*+json",
    } or value.endswith("+json")


class MarvelLcgHttpClient:
    """HTTP client for the explicitly supported marvel-lcg endpoints."""

    def __init__(
        self,
        base_url: str,
        password: str = "",
        *,
        timeout: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = self._validate_base_url(base_url)
        if not self.base_url:
            raise ValueError("marvel-lcg base URL is required")
        if not isinstance(password, str) or not password.strip():
            raise ValueError("MARVEL_LCG_PASSWORD must be non-empty")
        self.password = password
        self._version_ready = False
        self._owns_client = client is None
        self.cookie_jar = UnsafeCookieJar()
        self._scenario_paths: set[str] | None = None
        self._hero_paths: set[str] | None = None
        cookies = httpx.Cookies(self.cookie_jar)
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            cookies=cookies,
            timeout=timeout,
            follow_redirects=False,
        )
        # Construct the session token directly as well as supporting the HTML
        # client's /authenticate endpoint. This makes every gated request safe
        # even when the endpoint's response has no Set-Cookie header.
        if password:
            self._set_cookie("session_token", self.session_token_for(password))

    @staticmethod
    def _validate_base_url(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("marvel-lcg base URL is required")
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("marvel-lcg base URL must be an absolute HTTP URL")
        if parsed.query or parsed.fragment:
            raise ValueError(
                "marvel-lcg base URL must not contain query or fragment data"
            )
        lowered = value.lower()
        if any(
            token in lowered
            for token in ("debug", "cheat", "show", "replay", "hot_seat")
        ):
            raise ValueError(
                "marvel-lcg base URL must not contain debug, cheat, show, replay, or hot-seat parameters"
            )
        return value.rstrip("/")

    @staticmethod
    def session_token_for(password: str) -> str:
        return hashlib.md5(password.encode("utf-8")).hexdigest()

    @property
    def client(self) -> httpx.AsyncClient:
        return self._client

    @property
    def session_token(self) -> str | None:
        return self.session_token_for(self.password) if self.password else None

    def _set_cookie(self, name: str, value: str) -> None:
        cookies = getattr(self._client, "cookies", None)
        if cookies is None:
            return
        cookies.set(name, value, path="/")

    def cookie_header(self) -> str:
        """Return cookies for the render WebSocket handshake."""
        cookies = getattr(self._client, "cookies", None)
        if cookies is None:
            return ""
        values: dict[str, str] = {}
        for cookie in cookies.jar:
            values[cookie.name] = cookie.value
        return "; ".join(f"{name}={value}" for name, value in values.items())

    def _cookie_value(self, name: str) -> str | None:
        cookies = getattr(self._client, "cookies", None)
        if cookies is None:
            return None
        for cookie in cookies.jar:
            if cookie.name == name:
                return cookie.value
        return None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _validate_path(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        base_path = path.split("?", 1)[0]
        if base_path not in _ALLOWED_PATHS:
            raise ValueError(f"marvel-lcg endpoint is not allowlisted: {base_path}")
        if any(
            token in path.lower()
            for token in ("/debug", "cheat", "show", "replay", "hot_seat")
        ):
            raise ValueError(
                "marvel-lcg debug, cheat, show, replay, and hot-seat modes are forbidden"
            )
        return path

    async def _request(
        self,
        method: str,
        path: str,
        *,
        expected_types: Iterable[str],
        params: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        path = self._validate_path(path)
        if path.split("?", 1)[0] != "/get_version" and not self._version_ready:
            await self.get_version()
        with tracer.start_as_current_span(
            "marvel_lcg.http_request",
            attributes={
                "game.platform": "marvel-lcg",
                "http.request.method": method,
                "http.route": path.split("?", 1)[0],
            },
        ):
            try:
                response = await self._client.request(
                    method, path, params=params, **kwargs
                )
            except httpx.RequestError as exc:
                raise MarvelLcgError(
                    f"marvel-lcg {path.split('?', 1)[0]} request failed"
                ) from None
        content_type = _content_type(response)
        if content_type == "text/html":
            raise MarvelLcgAuthenticationError(
                f"marvel-lcg {path.split('?', 1)[0]} returned an HTML authentication/cache page"
            )
        allowed = {item.lower() for item in expected_types}
        if content_type not in allowed and not (
            content_type.endswith("+json")
            and any(item.endswith("+json") for item in allowed)
        ):
            raise MarvelLcgContentTypeError(
                f"marvel-lcg {path.split('?', 1)[0]} returned Content-Type {content_type or '<missing>'}; expected {sorted(allowed)}"
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise MarvelLcgHttpError(response.status_code, path.split("?", 1)[0])
        return response

    @staticmethod
    def _decoded_body(response: httpx.Response) -> bytes:
        body = response.content
        if (
            response.headers.get("content-encoding", "").lower() == "gzip"
            and body[:2] == b"\x1f\x8b"
        ):
            return gzip.decompress(body)
        return body

    async def get_version(self) -> str:
        response = await self._request(
            "GET", "/get_version", expected_types=("image/jpeg", "text/plain")
        )
        version = self._decoded_body(response).decode("utf-8").strip()
        if not version:
            raise MarvelLcgAuthenticationError(
                "marvel-lcg /get_version returned no app version"
            )
        if self._cookie_value("app_version") is None:
            self._set_cookie("app_version", version)
        self._version_ready = True
        return version

    async def authenticate(self) -> str | None:
        # This ordering is intentional: /get_version is the only gated call
        # guaranteed to work before the app_version cookie exists.
        await self.get_version()
        if not self.password:
            return None
        response = await self._request(
            "POST",
            "/authenticate",
            expected_types=("", "text/plain", "application/json"),
            json={"password": self.password},
        )
        token = self.session_token
        if token:
            self._set_cookie("session_token", token)
        return token

    async def _json(self, response: httpx.Response) -> Any:
        try:
            return json.loads(self._decoded_body(response).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise MarvelLcgError("marvel-lcg returned invalid JSON") from exc

    async def list_scenarios(self) -> list[str]:
        response = await self._request(
            "GET", "/list_scenarios", expected_types=("application/json",)
        )
        value = await self._json(response)
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise MarvelLcgError("marvel-lcg scenario listing is not a string array")
        self._scenario_paths = set(value)
        return value

    async def list_starter_deck(self) -> list[str]:
        response = await self._request(
            "GET", "/list_starter_deck", expected_types=("application/json",)
        )
        value = await self._json(response)
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise MarvelLcgError(
                "marvel-lcg starter-deck listing is not a string array"
            )
        self._hero_paths = set(value)
        return value

    def _document_path(self, path: str) -> str:
        if (
            not _SAFE_DOCUMENT_PATH.fullmatch(path)
            or path in {".", ".."}
            or ".." in path.split("/")
        ):
            raise ValueError("marvel-lcg document path is not a safe listed path")
        return quote(path, safe="/._- ")

    async def _get_document(self, endpoint: str, path: str) -> str:
        known_paths = (
            self._scenario_paths
            if endpoint == "/get_scenario_json"
            else self._hero_paths
        )
        if known_paths is not None and path not in known_paths:
            raise ValueError(
                f"marvel-lcg document path was not returned by its listing: {path!r}"
            )
        encoded = self._document_path(path)
        response = await self._request(
            "GET",
            f"{endpoint}?{encoded}",
            expected_types=("application/json", "text/plain"),
        )
        return self._decoded_body(response).decode("utf-8")

    async def get_scenario_json(self, path: str) -> str:
        return await self._get_document("/get_scenario_json", path)

    async def get_hero_json(self, path: str) -> str:
        return await self._get_document("/get_hero_json", path)

    async def new_game(
        self, descriptor: NewGameDescriptor | Mapping[str, Any]
    ) -> dict[str, Any]:
        if not isinstance(descriptor, NewGameDescriptor):
            descriptor = NewGameDescriptor(
                campaign_json=descriptor["campaign_json"],
                encounter_set_names=list(descriptor.get("encounter_set_names", [])),
                hero_json=list(descriptor["hero_json"]),
                seed=descriptor.get("seed") or 0,
                timeout=descriptor.get("timeout", 0),
                challenges=list(descriptor.get("challenges") or []),
                rules=(
                    [descriptor["rules"]]
                    if isinstance(descriptor.get("rules"), str)
                    else list(descriptor.get("rules") or ["v18_all"])
                ),
                campaign_log=descriptor.get("campaign_log") or {},
            )
        response = await self._request(
            "GET",
            "/new",
            expected_types=("application/json",),
            params={"data": json.dumps(descriptor.as_dict(), separators=(",", ":"))},
        )
        value = await self._json(response)
        if not isinstance(value, dict):
            raise MarvelLcgError("marvel-lcg /new returned a non-object response")
        return value

    def _seat(self, player_n: str | int) -> int:
        if isinstance(player_n, int):
            seat = player_n
        elif isinstance(player_n, str) and player_n.startswith("player"):
            try:
                seat = int(player_n[6:]) - 1
            except ValueError:
                seat = -1
        else:
            seat = -1
        if seat not in range(4):
            raise ValueError("marvel-lcg seat must be player1..player4")
        return seat

    async def get_world(self, player_n: str | int = "player1") -> dict[str, Any]:
        seat = self._seat(player_n)
        response = await self._request(
            "GET",
            "/get_world",
            expected_types=("application/json",),
            params={"p": seat},
        )
        value = await self._json(response)
        if not isinstance(value, dict):
            raise MarvelLcgError("marvel-lcg world is not an object")
        return value

    async def get_ask(self, player_n: str | int = "player1") -> dict[str, Any] | None:
        seat = self._seat(player_n)
        with tracer.start_as_current_span(
            "marvel_lcg.ask",
            attributes={
                "game.platform": "marvel-lcg",
                "game.seat": f"player{seat + 1}",
            },
        ) as span:
            response = await self._request(
                "GET",
                "/get_ask",
                expected_types=("application/json",),
                params={"p": seat},
            )
            value = await self._json(response)
            if value == {}:
                span.set_attribute("game.option.count", 0)
                return None
            if not isinstance(value, dict):
                raise MarvelLcgError("marvel-lcg ask payload is not an object")
            raw_options = value.get("options_json", "[]")
            if not isinstance(raw_options, str):
                raise MarvelLcgError("marvel-lcg options_json is not a JSON string")
            try:
                options = json.loads(raw_options)
            except (TypeError, ValueError) as exc:
                raise MarvelLcgError("marvel-lcg options_json is invalid JSON") from exc
            if not isinstance(options, list):
                raise MarvelLcgError(
                    "marvel-lcg options_json does not contain an array"
                )
            result = dict(value)
            result["options"] = options
            result.pop("options_json", None)
            span.set_attribute("game.option.count", len(options))
            return result

    async def post(
        self,
        player_n: str | int,
        option_id: int | str,
        targets: list[int | str],
        resources: list[int | str],
    ) -> None:
        seat = self._seat(player_n)
        body = quote(
            json.dumps(
                {"id": option_id, "targets": targets, "resources": resources},
                separators=(",", ":"),
            ),
            safe="",
        )
        await self._request(
            "POST",
            "/post",
            expected_types=("", "text/plain", "application/json"),
            params={"p": seat},
            content=body.encode("ascii"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    async def client_updated(
        self, player_n: str | int, render_id: int, game_id: int
    ) -> None:
        seat = self._seat(player_n)
        await self._request(
            "GET",
            "/client_updated",
            expected_types=("", "text/plain", "application/json"),
            params={"p": seat, "r": render_id, "g": game_id},
        )


# Descriptive compatibility aliases used by callers that refer to the engine's
# transport rather than its HTTP implementation detail.
MarvelLcgClient = MarvelLcgHttpClient
