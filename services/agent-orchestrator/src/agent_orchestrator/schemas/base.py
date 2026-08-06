from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictRequest(BaseModel):
    """Base for every request body this service accepts.

    Pydantic's default for a key a model does not define is to drop it, so a
    request carrying a field the server has never heard of is answered `200 OK`
    with the field silently discarded. DRA-53 is that failure in production: a
    current dashboard sent ``session_persona`` and ``allowed_subagents`` to an
    orchestrator predating them, the server stored neither, said nothing, and the
    user was told their subagent allowlist — which governs what the agent may
    spawn — had been narrowed when it had not.

    ``extra="forbid"`` turns that into a `422` naming the offending field. Its
    reach is asymmetric and worth stating: the check is performed by the *server*,
    so it only catches a field **this** server does not know. It protects against
    a client newer than an orchestrator that already carries this base; it can do
    nothing about an orchestrator older than the base itself, which is why the
    dashboard's own after-the-fact comparison (``unappliedSessionSettings``)
    stays.

    Inherit this on every request model. A field declared as an open mapping —
    ``metadata``, ``gateway_options``, ``provider_options`` — keeps accepting
    arbitrary contents: strictness is about the keys a model declares, not about
    the inside of a dictionary it declares as open.

    ``tests/unit/test_app_strict_request_bodies.py`` reads the app's own OpenAPI
    document and fails if any request body is missing this, so a model added later
    that forgets does not quietly reopen the hole.
    """

    model_config = ConfigDict(extra="forbid")
