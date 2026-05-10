"""Router: plugin card catalog search endpoint."""

from __future__ import annotations

import logging
import re
from inspect import Parameter, Signature

from fastapi import APIRouter, HTTPException, Query, Request

from game_service.api.models import (
    CardProviderMetadataResponse,
    CardResult,
    ListCardProvidersResponse,
    SearchCardsResponse,
)
from game_service.catalog.exceptions import (
    CardFilterValueError,
    UnknownCardProviderError,
    UnsupportedCardFilterError,
)
from game_service.catalog.service import (
    list_card_providers,
    get_card_provider,
    search_cards,
    supported_plugins,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["cards"])


@router.get(
    "/card-providers",
    response_model=ListCardProvidersResponse,
    operation_id="list_card_providers",
    summary="List supported game plugins and card providers",
)
async def list_supported_card_providers():
    providers = [
        CardProviderMetadataResponse.model_validate(item)
        for item in list_card_providers()
    ]
    return ListCardProvidersResponse(providers=providers)


def _provider_operation_suffix(provider_name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", provider_name).strip("_")


def _query_parameter_for_filter(filter_spec: dict):
    query_kwargs = {"description": filter_spec["description"]}
    if filter_spec["type"] == "integer":
        if filter_spec.get("minimum") is not None:
            query_kwargs["ge"] = filter_spec["minimum"]
        if filter_spec.get("maximum") is not None:
            query_kwargs["le"] = filter_spec["maximum"]
    default = filter_spec["default"] if "default" in filter_spec else None
    return Query(default=default, **query_kwargs)


def _annotation_for_filter(filter_spec: dict):
    annotation = {
        "string": str,
        "integer": int,
        "boolean": bool,
    }[filter_spec["type"]]
    if "default" not in filter_spec:
        return annotation | None
    return annotation


def _search_cards_response(provider_name: str | None, raw_filters: dict[str, str]):
    try:
        results = search_cards(plugin_name=provider_name, filters=raw_filters)
    except UnknownCardProviderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedCardFilterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except CardFilterValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    cards = [CardResult.model_validate(record.to_dict()) for record in results]
    return SearchCardsResponse(total=len(cards), cards=cards)


def _build_provider_search_endpoint(provider_name: str):
    provider = get_card_provider(provider_name)
    allowed_filter_names = {filter_spec["name"] for filter_spec in provider["filters"]}

    async def endpoint(request: Request, **filters):
        unknown_filters = sorted(set(request.query_params) - allowed_filter_names)
        if unknown_filters:
            allowed = ", ".join(sorted(allowed_filter_names))
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported filter {unknown_filters[0]!r} for provider {provider_name!r}. "
                    f"Allowed filters: {allowed}"
                ),
            )
        raw_filters = {key: value for key, value in filters.items() if value is not None}
        logger.info(
            "search_provider_cards: provider=%r filters=%r",
            provider_name,
            raw_filters,
        )
        return _search_cards_response(provider_name, raw_filters)

    endpoint.__name__ = f"search_cards_{_provider_operation_suffix(provider_name)}_endpoint"
    endpoint.__doc__ = (
        f"Search the {provider['display_name']} card catalog using provider-defined filters."
    )
    endpoint.__signature__ = Signature(
        parameters=[
            Parameter(
                "request",
                kind=Parameter.POSITIONAL_OR_KEYWORD,
                annotation=Request,
            )
        ]
        + [
            Parameter(
                filter_spec["name"],
                kind=Parameter.KEYWORD_ONLY,
                default=_query_parameter_for_filter(filter_spec),
                annotation=_annotation_for_filter(filter_spec),
            )
            for filter_spec in provider["filters"]
        ],
        return_annotation=SearchCardsResponse,
    )
    return endpoint


for provider_name in supported_plugins():
    provider = get_card_provider(provider_name)
    router.add_api_route(
        f"/cards/{provider_name}",
        _build_provider_search_endpoint(provider_name),
        response_model=SearchCardsResponse,
        operation_id=f"search_cards_{_provider_operation_suffix(provider_name)}",
        summary=f"Search {provider['display_name']} card catalog",
        methods=["GET"],
    )
