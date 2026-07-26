# Bifrost negative cache must not mask transient failures

## Why

`BifrostClient.list_models` negatively caches a provider's model listing whenever
`_list_models_uncached` raises a `BifrostError`, using the full
`BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS` TTL (default 600s) REGARDLESS of whether
the failure is retryable. But the client already classifies transient failures —
timeouts, network errors, 5xx, and 429 — as `retryable=True`. A single transient
blip therefore suppresses the provider for up to 10 minutes: every subsequent
`list_models` call fast-fails from the negative marker even after the provider
has recovered, and `/providers` keeps reporting it `available=false`.

The negative cache exists to avoid re-incurring the slow per-provider list-models
timeout for a provider that is definitively unreachable (e.g. missing API key —
a non-retryable auth failure). That benefit should be preserved for definitive
failures, but a transient failure must recover quickly rather than being pinned
unavailable for the full definitive TTL.

## What Changes

- **agent-orchestrator (Bifrost negative cache)** — a retryable/transient
  failure SHALL be negatively cached with a much shorter TTL
  (`BIFROST_UNAVAILABLE_RETRYABLE_CACHE_TTL_SECONDS`, default 30s) while a
  definitive (non-retryable) failure keeps the long
  `BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS` TTL. This bounds re-probe latency for a
  brief outage without re-incurring the slow timeout on every call, and without
  permanently hiding a recovered provider.
- Existing invariants are preserved: a successful listing still clears the
  negative marker, `clear_model_cache` still flushes positive and negative keys,
  and the negative-cache short-circuit read path is unchanged.

## Impact

- Affected specs: `agent-orchestrator` (Cached unavailable providers — retryable
  vs. definitive TTL).
- Affected code:
  `services/agent-orchestrator/src/agent_orchestrator/integrations/bifrost.py`
  (retryable-aware negative TTL selection),
  `services/agent-orchestrator/src/agent_orchestrator/config.py`
  (new `BIFROST_UNAVAILABLE_RETRYABLE_CACHE_TTL_SECONDS` setting + validator),
  `services/agent-orchestrator/src/agent_orchestrator/runtime/app.py` (wiring).
- No API or schema changes; internal correctness hardening plus one new config
  knob with a safe default.
