# Refuse a request field the agent-orchestrator does not know

## Why

DRA-53 was reproduced end to end: a current dashboard sent
`{"session_persona": …, "allowed_subagents": [ … ]}` to an agent-orchestrator
built before DRA-38. The server answered `200 OK`, stored neither field, and
returned a session carrying neither. Nothing anywhere reported a problem, and the
user was told the save succeeded — on an allowlist that governs what the agent may
spawn.

The enabler is that **no request body in the agent-orchestrator rejects a field it
does not know**. Not one of its fifteen request models sets `extra`, so Pydantic's
default applies and an unknown key is dropped in silence; `POST /skills` does not
even have a model, taking `dict[str, Any]` and reading two keys out of it.

DRA-53 fixed the dashboard half — `unappliedSessionSettings()` compares what the
save asked for against what the server reports and says "Save incomplete". That
defence is the right one for the dashboard and is deliberately left alone here: it
catches a refusal for any reason, not only skew. But it lives in one client,
compares two named fields, and generalises to nothing. Every other caller of this
API — a script, the generated MCP surface, a second dashboard — has nothing.

A server can only refuse what it can see is wrong, and a field it has never heard
of is the one thing it can always see is wrong. Refusing it costs one line per
model and turns the next skew of this kind from silence into a `422` naming the
field.

## What Changes

### The agent-orchestrator rejects unknown request-body fields

Every request body the agent-orchestrator accepts is declared strict: a key the
model does not define is a `422` naming that key, instead of being dropped.

This is stated once, as a rule about the service, rather than as a property of two
models. Every request model inherits a single `StrictRequest` base, and a test
built from the running app's own OpenAPI schema asserts that every request body
the service exposes declares `additionalProperties: false` — so a request model
added later that forgets the base fails the suite rather than quietly reopening
the hole.

`POST /skills`, the one endpoint with no request model at all, gains one. Its
existing error contract is preserved exactly: a body with no `name` is still a
`400`, not a `422`, because the check that produces it is a check on the value and
not on the shape.

Free-form fields stay free-form. `metadata`, `gateway_options` and
`provider_options` are `dict[str, Any]` by design, and strictness applies to the
model's own keys, not to the contents of a dictionary a field declares as open.

### What this does and does not protect

It does **not** fix the deployment that produced DRA-53, and no server-side change
could. `extra="forbid"` fires when the *server* does not know a field, so it
protects only against a server at or after this change; the orchestrator in that
deployment predates it and will keep answering `200`. The DRA-53 client-side
comparison remains the only thing that covers that case, which is why it stays.

What it protects is every skew from this commit onward, for every client, with no
client cooperation required.

## Capabilities

### Modified Capabilities

- `agent-orchestrator` — a request body carrying a field the service does not
  define is refused with `422` naming the field, rather than accepted with the
  field discarded.

## Impact

- **agent-orchestrator** — `schemas/base.py` is new and holds the strict base;
  every request model in `schemas/` inherits it; `api/routers/sessions.py` gains a
  model for `POST /skills`.
- **No MCP surface change.** Measured in this tree rather than assumed — see
  `design.md`. The generated tool schema does not carry `additionalProperties`,
  and an unknown tool argument is dropped by FastMCP's request director before an
  HTTP request is built, so `extra="forbid"` can neither break nor protect a tool
  call.
- **No dashboard change.** Its session payloads are declared field by field in
  `features/play/lib/client-api.ts`; no in-tree caller sends a key the
  orchestrator does not define.
- **No other service changes.** history-service's `EventEnvelope` is
  `extra="allow"` because the `history-event-store` spec requires it to tolerate
  unknown forward-compatible fields; tightening it would break a stated
  requirement. eval-service and game-service share the gap and are filed, not
  fixed here.

## Non-goals

- **No version or capability endpoint.** It is the stronger fix for DRA-53's
  direction — a client that asks a server what it supports learns the answer
  before it sends anything, and a `404` on the endpoint is itself the signal that
  the server is old — but it is a new public surface with its own design, and it
  helps only clients that ask. Filed as a follow-up. The two are complementary,
  not alternatives.
- **No `ignored_fields` or `warnings` echo on the response.** Weighed and
  rejected; the reasoning is in `design.md`.
- **No change to the DRA-53 dashboard comparison.** It covers a case this change
  cannot, and duplicating it here would give two answers to one question.
- **No tightening of history-service's event envelope or import bundles**, which
  are deliberately and specifically lenient.
