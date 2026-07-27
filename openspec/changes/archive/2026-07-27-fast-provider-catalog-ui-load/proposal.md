# Provider catalog must not delay the dashboard's first paint

## Why

Opening the Play workspace on a cold provider cache took ~7 seconds during which
the page showed nothing but a spinner. Two independent causes compound:

1. **The dashboard blocks its first paint on `/providers`.**
   `usePlaySessionLoader` awaited `Promise.allSettled([config, providers,
   skills, sessions])` before calling `setConfig`/`setDraft`, and
   `PlayWorkspace` renders a bare `Spinner` until both exist. `allSettled` makes
   the load *resilient*, but it still waits for the slowest call — so the whole
   workspace was gated on the slowest thing in the system.

2. **Bifrost's model listing waits on an unreachable `lmstudio`.**
   Measured against the running stack: every provider listing takes ~6.5-7.5s
   even with *no* API keys configured at all. Bifrost's list-models endpoint
   fans out to every provider in `services/bifrost/config.json` and only answers
   once the slowest one finishes. Providers without a key fail immediately
   ("no valid keys found for provider"), so they are not the cause. The cost is
   `lmstudio`, which has a hardcoded `dummy` key and therefore is always probed:
   when LM Studio is not running on the host, each attempt fails instantly but
   `max_retries: 3` with `retry_backoff_initial: 1000` / `retry_backoff_max:
   10000` spends ~6s purely in backoff before giving up. A throwaway Bifrost
   container running the same config with zero keys reproduced 7.9s / 6.7s /
   7.0s; with the retry policy tightened it returned in 0.23s / 0.22s / 0.21s.

The reported symptom is attributed to `ENABLED_PROVIDER_IDS`, but Bifrost fans
out to its own configured providers regardless of that list; a longer
`ENABLED_PROVIDER_IDS` only multiplies how many identical listings the
orchestrator requests, it does not change the per-listing latency.

## What Changes

- **dashboard (initial load)** — the provider catalog SHALL be fetched off the
  blocking initial-load path. The workspace renders as soon as configuration,
  skills, and sessions resolve, seeded from the configuration defaults; the
  catalog is applied when it arrives, at which point the provider/model
  selectors are re-seeded to a working provider and the unavailable-provider
  notice is updated. The re-seed SHALL NOT overwrite a draft the user already
  edited or one a loaded session has committed.
- **infrastructure (Bifrost gateway configuration)** — the `lmstudio` provider
  SHALL use a fast-failing retry policy (`max_retries: 1`,
  `retry_backoff_initial: 200`, `retry_backoff_max: 1000`) so that an absent
  local LM Studio cannot hold the gateway's cross-provider model listing for
  seconds. LM Studio is a local endpoint reached over the Docker network; a
  long, slowly-backing-off retry ladder buys nothing there.
- Existing behaviour is preserved: a failed `/providers` fetch is still a
  non-blocking notice rather than a fatal error, a failed configuration fetch is
  still the sole fatal failure, and the orchestrator's per-provider timeout,
  guard margin, and positive/negative Valkey caches are unchanged.

## Non-goals

- Changing the orchestrator's `/providers` contract, its per-provider timeout,
  or its Valkey caching. The positive cache already makes warm calls ~6ms
  (measured), so the cold path is the only slow one and it is now off the UI's
  critical path.
- De-duplicating the orchestrator's N identical per-provider listing requests.
  Bifrost ignores the `x-bf-list-models-provider` header and returns the same
  full cross-provider payload for each, so collapsing them would cut gateway
  load but not wall-clock latency (the calls are already concurrent). Recorded
  here as a known inefficiency rather than fixed, to keep this change small.
- Reporting a provider that contributes zero models as `available=false`. That
  is a separate catalog-accuracy question with its own established tests.

## Impact

- Affected specs: `dashboard` (Resilient provider and model loading),
  `infrastructure` (Bifrost gateway configuration).
- Affected code:
  `services/dashboard/features/play/lib/use-play-session-loader.ts`
  (catalog moved off the blocking load, applied asynchronously),
  `services/bifrost/config.json` (`lmstudio` retry policy).
- No API, schema, or configuration-variable changes. Picking up the gateway
  change requires recreating the `bifrost` container.
