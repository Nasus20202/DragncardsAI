## Context

The agent-orchestrator exposes the enabled provider set through `Settings.enabled_provider_ids`, derived from the `ENABLED_PROVIDER_IDS` environment variable (falling back to all supported providers). The running app stores its settings on `app.state.settings`, so tests already have a reliable, in-process source of truth for which providers are enabled.

The failing tests instead embedded literal provider ids (`openai`, `gemini`) into their assertions and request bodies. When a deployment narrows `ENABLED_PROVIDER_IDS`, these literals no longer match the configured providers and the tests fail despite correct behavior.

## Goals / Non-Goals

**Goals:**
- Tests pass regardless of which providers are enabled in the environment.
- Tests still prove provider listing, valid-provider session model-config assignment, and disabled-provider rejection.

**Non-Goals:**
- Changing production provider configuration or validation behavior.
- Adding new provider integrations.

## Decisions

**Decision**: Derive expectations from `app.state.settings.enabled_provider_ids`.
- **Rationale**: It is the same source the API uses, so the test asserts against the app's actual configuration rather than a guessed default.
- **Alternatives considered**: Re-reading `ENABLED_PROVIDER_IDS` directly in the test — rejected because it duplicates parsing logic and can drift from `Settings`.

**Decision**: For the rejection test, pick a provider that is supported but not enabled.
- **Rationale**: Keeps the test meaningful (the provider is a real, known provider that is simply disabled) and avoids relying on the previously hardcoded `mistral`. If every supported provider happens to be enabled, the test skips rather than failing spuriously.

**Decision**: Let the shared unit `app` fixture honor `ENABLED_PROVIDER_IDS` from the environment.
- **Rationale**: Lets the existing suite be exercised under a reduced provider set (e.g. OpenAI disabled) without code changes, mirroring real deployments.

## Risks / Trade-offs

- **Risk**: A test picking "the first enabled provider" could mask a provider-specific bug.
- **Mitigation**: Provider-specific behaviors (model prefixing, unavailability) remain covered by dedicated tests that explicitly configure those providers via the `enabled_provider_ids` fixture parameter.
