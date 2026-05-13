from __future__ import annotations

from typing import Any

from game_service.logic.actions import ACTION_TYPES


def build_action_catalog_entries() -> list[dict[str, Any]]:
    return [
        {
            "type": model_cls.model_fields["type"].default,
            "description": (model_cls.__doc__ or "").strip(),
            "schema": model_cls.model_json_schema(),
        }
        for model_cls in ACTION_TYPES
    ]
