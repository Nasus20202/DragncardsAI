## 1. Orchestrator capability parsing and catalog

- [x] 1.1 Extend the Bifrost model metadata value objects and rich `/v1/models` parsing to preserve reasoning fields, including `supported_efforts=None` when absent and `supported_efforts=[]` when explicitly empty; verify with focused Bifrost parser/cache tests.
- [x] 1.2 Enrich provider-scoped model listings from the cached rich model catalogue and expose optional `model_capabilities` additively in the `/providers` response; verify absent, non-empty, and explicit-empty payloads through the catalog endpoint.
- [x] 1.3 Update orchestrator catalog documentation and fixtures for the additive capability mapping while retaining compatibility with identifier-only provider responses; verify existing provider filtering and LM Studio fixtures still pass.

## 2. Orchestrator reasoning validation

- [x] 2.1 Add shared server-side validation for reasoning efforts using the selected provider/model capability state, with legacy low/medium/high fallback, exact non-empty advertised values, and explicit-empty rejection; apply it to session, player-seat, and persona configuration writes.
- [x] 2.2 Add focused API tests proving accepted legacy and advertised efforts, rejected unsupported efforts, and explicit-empty requests that contain no effort; verify invalid configurations are not persisted.

## 3. Dashboard model-aware controls

- [x] 3.1 Extend dashboard provider/catalog types and shared model helpers to resolve advertised effort options with the same absent/non-empty/empty tri-state semantics.
- [x] 3.2 Update Play settings, Evaluate judge settings, and persona settings to derive effort options from the selected model, reset stale efforts on model changes, and disable/omit reasoning effort for explicit-empty capabilities; verify with focused component/helper tests.
- [x] 3.3 Update dashboard fixtures and existing model-picker tests for additive catalog capabilities and arbitrary advertised effort strings while preserving LM Studio/legacy fallback behavior.
