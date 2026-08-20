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
    enum_vals = layout_schema.get("enum")
    if enum_vals is None:
        enum_vals = next(
            (
                item.get("enum")
                for item in layout_schema.get("anyOf", [])
                if "enum" in item
            ),
            None,
        )
    assert enum_vals == [
        "standard1Player",
        "standard2Player",
        "standard3Player",
        "standard4Player",
    ]
