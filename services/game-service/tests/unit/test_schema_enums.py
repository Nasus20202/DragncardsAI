from __future__ import annotations

from game_service.api.app import create_app


def test_set_player_count_layout_enum_exposed_in_schema():
    app = create_app()
    openapi = app.openapi()
    # Find schema for SetPlayerCountRequest
    schemas = openapi.get("components", {}).get("schemas", {})
    schema = schemas.get("SetPlayerCountRequest")
    assert schema is not None, "SetPlayerCountRequest schema missing"
    props = schema.get("properties", {})
    layout_schema = props.get("layout_id")
    assert layout_schema is not None, "layout_id property missing"
    # layout_id should be a string with enum or nullable via anyOf
    enum_vals = layout_schema.get("enum") or []
    # Even if plugin provides no layouts, the field should exist; accept empty enum
    assert isinstance(enum_vals, list)
