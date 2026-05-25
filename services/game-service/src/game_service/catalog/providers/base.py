"""Shared provider contracts and normalized provider metadata structures."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class FilterSpec(TypedDict):
    name: str
    type: Literal["string", "integer", "boolean"]
    description: str
    default: NotRequired[Any]
    minimum: NotRequired[int]
    maximum: NotRequired[int]
    match: NotRequired[str]


@dataclass(frozen=True)
class NamedActionList:
    id: str
    action_list: Any


@dataclass(frozen=True)
class HotkeyAction:
    scope: str
    key: str
    label: str | None = None
    action_list: Any = None
    token_type: str | None = None


@dataclass(frozen=True)
class TouchBarAction:
    id: str
    row: int
    order: int
    action_type: str
    label: str | None = None
    action_list: Any = None
    token_type: str | None = None
    image_url: str | None = None


@dataclass(frozen=True)
class DefaultCardAction:
    label: str | None = None
    action_list: Any = None
    condition: Any = None
    position: str | None = None


@dataclass(frozen=True)
class PlayerCountLayout:
    label: str
    num_players: int
    layout_id: str | None = None


@dataclass(frozen=True)
class PluginActionCatalog:
    named_action_lists: list[NamedActionList] = field(default_factory=list)
    hotkeys: list[HotkeyAction] = field(default_factory=list)
    touch_bar: list[TouchBarAction] = field(default_factory=list)
    default_actions: list[DefaultCardAction] = field(default_factory=list)
    player_count_layouts: list[PlayerCountLayout] = field(default_factory=list)
    load_groups: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CatalogCardAttributes(BaseModel):
    """Provider-specific card attributes normalized into a typed object."""

    model_config = ConfigDict(extra="allow", frozen=True)


class CatalogCardRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    database_id: str
    name: str
    subname: str | None = None
    type_code: str | None = None
    classification: str | None = None
    traits: list[str] = Field(default_factory=list)
    official: bool
    attributes: CatalogCardAttributes = Field(default_factory=CatalogCardAttributes)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class CatalogProvider(ABC):
    """Provider interface for card search and plugin action metadata."""

    @property
    @abstractmethod
    def plugin_name(self) -> str: ...

    @property
    @abstractmethod
    def display_name(self) -> str: ...

    @property
    @abstractmethod
    def filters(self) -> list[FilterSpec]: ...

    @abstractmethod
    def load_card_db(self) -> list[CatalogCardRecord]: ...

    @abstractmethod
    def search_cards(self, filters: dict[str, Any]) -> list[CatalogCardRecord]: ...

    def load_sets(self) -> list[dict[str, Any]]:
        return []

    def search_sets(
        self, name: str | None = None, type: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    def get_load_groups(self) -> list[str]:
        return []

    def get_action_catalog(self) -> PluginActionCatalog:
        return PluginActionCatalog(load_groups=self.get_load_groups())
