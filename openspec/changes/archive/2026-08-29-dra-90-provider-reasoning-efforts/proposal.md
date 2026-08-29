## Why

The provider catalog currently exposes model identifiers without the reasoning-effort capabilities reported by Bifrost. As a result, the dashboard offers `low`/`medium`/`high` for every model, while providers such as LM Studio may advertise a different set or explicitly no reasoning support. Preserving Bifrost's optional capability metadata lets users select only supported efforts without breaking existing providers whose catalog entries have no metadata.

## What Changes

- Parse optional reasoning capability metadata from each rich Bifrost `/v1/models` model entry, preserving the distinction between absent metadata, non-empty advertised efforts, and an explicitly empty effort list.
- Carry model-level reasoning capabilities through the agent-orchestrator provider catalog response and dashboard provider types.
- Validate configured reasoning efforts against the selected model's advertised values when those values are present; retain `low`/`medium`/`high` validation when metadata is absent and reject reasoning settings when the model explicitly advertises no efforts.
- Make Play and Evaluate model/reasoning controls derive their effort options from the selected model, while retaining the legacy options for models without metadata.
- Omit `reasoning_effort` from requests when the selected model explicitly does not support reasoning.
- Keep LM Studio and other current catalog entries compatible when Bifrost omits reasoning metadata.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-orchestrator`: provider model catalog responses and reasoning configuration validation now honor optional model capabilities.
- `dashboard`: provider/model selection and reasoning controls now use model-specific advertised effort values with legacy fallback.

## Non-goals

- Do not change DragnCards or Marvel LCG turn scheduling or game orchestration.
- Do not change Bifrost provider configuration, model discovery endpoints, or the request transport beyond the reasoning option selected by the orchestrator.
- Do not infer capabilities by provider name or hardcode a provider-specific effort list.
- Do not remove compatibility with existing responses that omit reasoning metadata.
