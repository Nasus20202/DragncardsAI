## Context

The current orchestrator catalog returns `models` as a list of strings, while Bifrost's rich `/v1/models` response carries an optional `reasoning` object with `supported_efforts`. Existing sessions and current LM Studio entries do not include this metadata, and the dashboard currently hardcodes the three legacy effort values. See `proposal.md` for the motivation and user-facing scope.

## Goals / Non-Goals

**Goals:**

- Preserve model identifiers and existing catalog consumers while making model reasoning metadata available to newer clients.
- Keep the three-state distinction required for safe request construction: unavailable metadata, non-empty advertised efforts, and explicit empty efforts.
- Apply the same effort-option behavior to Play, Evaluate, and persona model selectors.
- Reject unsupported configured efforts at the orchestrator boundary before persistence.

**Non-Goals:**

- No changes to Bifrost itself, provider configuration, or game turn orchestration.
- No new persistence columns or migrations; capabilities are discovery data, not session state.
- No provider-specific hardcoded effort tables.

## Decisions

### Preserve the catalog wire shape additively

Keep `ProviderResponse.models` as `list[str]` and add an optional `model_capabilities` mapping keyed by model id. Each mapping value carries the optional Bifrost reasoning object. This avoids breaking existing dashboard and API consumers while allowing clients that understand the field to select model-specific efforts. Alternatives rejected: replacing strings with model objects would require a coordinated breaking migration across every picker and test fixture; adding a second endpoint would allow the model list and capabilities to drift and would not satisfy a single catalog response.

### Normalize only the supported reasoning fields

Represent Bifrost's `reasoning` object with a typed response shape containing its optional `mandatory`, `default_enabled`, `supported_efforts`, and `default_effort` fields. Preserve `supported_efforts=None` when the key is absent and `supported_efforts=[]` when it is explicitly present. Alternatives rejected: coercing with `or []` loses the absent/empty distinction; passing an untyped arbitrary map makes the API contract and dashboard handling unclear.

### Enrich provider listings from the rich all-models endpoint

Continue using the provider-scoped compatibility listing for the model identifier set and cache, then enrich matching entries from the rich `/v1/models` listing when available. A failed rich lookup degrades to identifiers with unavailable metadata, preserving current providers and LM Studio behavior. The all-models cache stores the enriched objects, so repeated context and catalog reads do not require a second rich request per model. Alternatives rejected: replacing the provider-scoped endpoint would change routing semantics for providers that return unqualified ids; one rich lookup per model would create avoidable latency and gateway load.

### Validate at each configuration boundary

Use one orchestrator helper to inspect the configured provider/model's advertised efforts and validate any submitted `reasoning.effort`. Call it from session model configuration, player configuration, and persona configuration routes. A missing or failed capability lookup uses the legacy set; a non-empty list is authoritative; an empty list rejects an effort. Alternatives rejected: relying only on Pydantic's static literal prevents provider values such as `minimal` and cannot detect explicit no-support; validating only in the dashboard leaves HTTP/MCP callers able to persist invalid settings.

### Derive options from the selected model in shared dashboard helpers

Add typed catalog capability helpers that return the exact effort list or legacy fallback and use them in Play, Evaluate, and persona controls. When the list is empty, clear/disable the reasoning toggle and omit the effort key from assembled gateway options. Alternatives rejected: duplicating provider/model lookups in each component risks inconsistent fallback semantics; silently retaining a stale effort would cause a server rejection after a model change.

## Risks / Trade-offs

- Bifrost versions before the rich metadata field, and providers such as LM Studio, produce no reasoning metadata; the fallback intentionally remains the existing low/medium/high behavior.
- The rich endpoint is upstream-controlled and may be unavailable while the compatibility listing works. Enrichment is therefore best-effort, and configuration validation must not turn a temporary metadata outage into an outage for legacy-compatible models.
- Bifrost may omit an explicitly empty list during its own JSON serialization because the upstream schema uses `omitempty`; the parser still preserves an explicit empty list whenever it is received, which protects the contract and test doubles.
- Provider model ids may be qualified differently between endpoints. Enrichment matches exact ids first and then the provider-qualified form of an unqualified compatibility id; unmatched entries retain absent metadata rather than guessing.
