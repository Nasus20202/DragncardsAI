# Design: refusing an unknown request field

## Context

Pydantic v2's default for an undeclared key is `extra="ignore"`. Every request
body in the agent-orchestrator takes that default, so a `PATCH /sessions/{id}`
carrying a field the server has never heard of is answered `200 OK` with the field
discarded and nothing said. DRA-53 is that failure observed in production: a
current dashboard against a pre-DRA-38 orchestrator, an allowlist that governs
what an agent may spawn silently not narrowed, and a status line reading
"Configuration saved".

Three options were on the table. All three change an HTTP contract, which is why
this was filed separately from DRA-53 rather than ridden in on it.

## Goals / Non-Goals

**Goals**

- A field the server does not know is refused, loudly, with the field named.
- The rule is stated once about the service, not bolted onto the two models that
  happened to be involved in one bug report.
- A request model added later cannot silently reopen the hole.
- No client in this repository breaks.

**Non-Goals**

- Fixing the deployment that produced DRA-53. Out of reach by construction; see
  "The asymmetry" below.
- Version negotiation. Named as a follow-up, not attempted here.
- Tightening the services whose leniency is deliberate and spec-backed.

## The asymmetry, stated plainly

`extra="forbid"` is a check the **server** performs. It fires when the server does
not recognise a field. So it protects exactly one direction of skew: **client
newer than server** — and only when the server is at or after this change.

The orchestrator that produced DRA-53 predates this change. It will go on
answering `200` and discarding fields until it is rebuilt, and nothing committed
here alters that. **This change does not fix the incident that motivated it. It
fixes every recurrence after it.**

That is not a defect in the option; it is a property of the problem. An old server
cannot be taught to reject fields it does not know about, because the teaching
would have to be in the old server. Only two things can cover that direction:

- the client checking afterwards whether the write took effect — which is what
  DRA-53 landed, and why it stays; and
- the client asking beforehand what the server supports — a capability endpoint,
  which is the follow-up below.

Anyone reading this expecting DRA-53's deployment to be fixed by it should read
the previous three paragraphs again. It is not.

## Decisions

### Decision: `extra="forbid"` on every request body, not on two models

Chosen over the alternatives below.

The failure DRA-53 exposed is not "these two fields are droppable"; it is "this
service drops fields". Hardening `SessionUpdateRequest` and `SessionCreateRequest`
alone would leave thirteen siblings — `PromptRequest`, `PersonaRequest`,
`PlayerConfigRequest`, `ModelConfigRequest`, `McpRegistryRequest`,
`SubagentAllowanceRequest`, and the rest — with the identical behaviour, several
of them writing configuration just as consequential as the allowlist.
`PersonaRequest.allowed_tools` is a tool allowlist; `PlayerConfigRequest.persona`
decides what a seat runs as. A rule that covers one endpoint is a rule nobody can
state and nobody will remember to extend.

Mechanically: a `StrictRequest` base in `agent_orchestrator/schemas/base.py`,
inherited by every request model, plus a test that reads the app's own OpenAPI
document and asserts that every schema referenced by a `requestBody` declares
`additionalProperties: false`. The test is what makes this durable — the base
class is easy to forget, and the assertion is derived from the running app rather
than from a hand-maintained list, so a new endpoint is covered the day it lands.

**Cost, accepted:** a newer client against a server at or after this change gets
`422` on the whole request instead of a partially applied save. That is a real
downgrade in availability for that endpoint and it was not waved away. It is
accepted because a "partially applied save" of a security control is not a working
save — it is a false report of one — and because the failure is now legible: the
`422` names the field, which is more than the DRA-53 comparison can do (it can say
"the allowed subagents did not apply", not "your server has no such field"). The
dashboard already routes both outcomes to the same error area, so the user-visible
difference is a better message, not a new kind of breakage.

**Blast radius, measured rather than assumed:** the dashboard declares its session
payloads field by field in `services/dashboard/features/play/lib/client-api.ts`;
no in-tree caller sends a key the orchestrator does not define. **Nothing broke** —
all 691 pre-existing unit tests and all 31 integration tests pass unchanged, and
no test needed editing. That is worth recording rather than glossing: it was
expected that some test posting a superset of fields would start returning `422`,
and none does. The contract this change enforces was already the contract every
caller in this repository was keeping; it simply was not being checked.

### Decision: reject the `ignored_fields` / `warnings` echo

The middle option — keep accepting unknown fields, but list them back on the
response so a client can notice — was weighed seriously and rejected on three
grounds.

**It reproduces the original bug one level up.** A client would have to read the
*absence* of `ignored_fields` as "nothing was dropped". But absence also means
"this server is too old to report drops" — which is the precise ambiguity DRA-53
was made of. The archived DRA-53 proposal says it in as many words about a missing
field: *"An orchestrator predating a setting answers 200 OK and omits the field,
which is byte-for-byte what 'cleared' looks like; conflating the two is precisely
how a discarded write passes for a successful one."* An `ignored_fields` key
inherits that property whole.

**It defaults to silence.** A caller that does not look still gets `200` and still
believes the write landed. The whole point is the caller who is not looking —
every caller that is looking already has the DRA-53 pattern available to it.
`extra="forbid"` needs no client cooperation at all.

**It is the larger contract change, for the weaker guarantee.** Adding a field to
every session response touches more of the API than adding a config line to every
request model, and it changes what response consumers must tolerate.

The one thing it has over the chosen option — a request that half-works rather
than not working — is the thing that caused the incident.

### Decision: give `POST /skills` a model, and keep its `400`

It is the one endpoint the rule cannot otherwise cover: it takes `dict[str, Any]`
and reads `name` and `metadata` out of it, so every other key in the body is
already discarded with no model to make strict.

The model declares `name: str | None = None`, and the handler keeps its existing
`400 "name is required"` check. Declaring `name: str` as required would have been
tidier and would have moved that error to `422`, which is a gratuitous contract
change on an endpoint this change is only passing through. The shape check becomes
strict; the value check stays exactly where and what it was.

### Decision: no capability or version endpoint here — filed instead

This deserves the plainest possible statement, because it is the option that
actually addresses DRA-53's direction: **a client that asks a server what it
supports before sending finds out about skew even when the server is older than
every fix**, since a `404` on the endpoint is itself a conclusive answer. That is
strictly more than `extra="forbid"` can do.

It is not done here because it is a new public surface with its own unanswered
questions — what names a capability, who maintains the list, whether it is a
version string (which invites clients to compare versions instead of asking about
features) or a feature list (which someone has to remember to add to) — and
because it helps only clients that ask, whereas the chosen change needs no client
cooperation. The two are complementary: one stops a bad request, the other stops
the request being made. Filed as a follow-up on the DRA-56 issue.

### Decision: leave the other services alone, and say why for each

- **history-service `EventEnvelope`** — `ConfigDict(extra="allow")`, and the
  `history-event-store` spec *requires* it: "Tolerate unknown forward-compatible
  fields … SHALL persist the envelope without failing on the unknown fields."
  Tightening it would break a stated requirement. Correctly lenient: an event
  writer that is newer than the store must not lose events.
- **history-service import bundles** (`schemas/transfer.py`) — five records at
  `extra="ignore"`, documented in the file as forward-compatibility for a bundle
  written by a newer service. Same reasoning, deliberately chosen, left alone.
- **eval-service** — one request body, `EvaluationRequestBody`, with three nested
  models. Same gap, and a typo like `round` for `rounds` currently degrades into a
  confusing "must specify at least one of" instead of naming the key. Small and
  worth doing; filed rather than done, because it is a second service's HTTP
  contract and does not belong in a change whose spec delta is scoped to the
  orchestrator.
- **game-service** — the largest instance of the gap: twenty-five action models
  behind a discriminated union, each also a request body on its own helper
  endpoint. Also the highest-stakes: a mistyped argument to `move_card` currently
  executes a *different, legal* move rather than erroring, which is worse than the
  orchestrator's failure mode. But it sits on the game agent's hot path, the agent
  reaches it through MCP, and turning a dropped argument into a `422` mid-game is
  a behaviour change that needs its own evaluation run. Filed, not ridden in.

The line drawn is: one service's request contract per change, and never against a
leniency the specs require.

## Risks / Trade-offs

- **A future client sending a field a current server lacks now fails hard.**
  Accepted; the reasoning is above. Mitigated for the one client that has a
  degraded path already (the dashboard reports it in the same place, with a better
  message).
- **The MCP surface barely moves.** Measured before and after the change, not
  assumed, in this tree with `fastmcp 3.4.5` and `pydantic 2.13.4`:
  - The OpenAPI components *do* gain `additionalProperties: false`.
  - The generated MCP **tool** schema does **not** gain it at the root, for any
    tool. `_combine_schemas_and_map_params` in
    `fastmcp/utilities/openapi/schemas.py` flattens the body's properties
    alongside the path parameters into a freshly built
    `{"type": "object", "properties": …, "required": …}` and never copies
    `additionalProperties` from the body schema.
  - It **is** carried through on a *nested* model, which is copied as a property
    schema verbatim. Exactly two tools change, both by one nested node:
    `compact_session` at `properties.request.anyOf[0]` and `save_session_player`
    at `properties.reasoning.anyOf[0]`. No tool is added, removed or renamed.
  - Those two nodes are the only place the MCP surface gains anything: a bogus
    key inside a `reasoning` object is now refused by the tool schema itself.
  - Everywhere else, an unknown tool argument never reaches HTTP in any case:
    `fastmcp/utilities/openapi/director.py` drops any argument absent from the
    route's `parameter_map` with a `logger.warning` and continues, so it is never
    written into the request body and the server never sees it.

  So the MCP surface is neither broken nor meaningfully protected by this change.
  `additionalProperties: false` in a tool schema is also the *stricter* direction
  for MCP clients — FastMCP keeps it by default because, in its own words, "some
  clients (e.g. Claude) require `additionalProperties: false` for strict
  validation" — so the two nodes that do change change safely.

  That the surface has its own silent drop — a discarded argument is a log line on
  the server and a successful tool result to the model — is a separate defect,
  filed as a follow-up.
- **The base class is easy to forget on a new model.** Mitigated by the
  OpenAPI-derived test rather than by review discipline.
- **`metadata` and the option dictionaries remain open.** By design: they are
  declared `dict[str, Any]`, and strictness is about a model's own keys. A caller
  can still park an unrecognised setting inside `metadata` and have it ignored —
  but that is what an open dictionary means, and it is stated in the spec so it is
  not mistaken for an oversight.

## Migration

None. No stored data, no schema migration, no configuration. The change is
observable only to a caller sending a field the service does not define, and no
such caller exists in this repository.

## Open questions

None. The three things deliberately left are filed rather than left open here:

- **DRA-59** — the capability/version endpoint, the option that covers the
  direction this change cannot.
- **DRA-60** — eval-service's `EvaluationRequestBody` and game-service's action
  models, with a note on which leniency is spec-required and must not be touched.
- **DRA-61** — the MCP surface's own silent argument drop.
