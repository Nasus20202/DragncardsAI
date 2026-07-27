## 1. Diagnose the stall

- [x] 1.1 Time `/providers` against the running stack (cold ~7.6s, warm ~6ms) and
      confirm the positive Valkey cache already makes repeat calls fast.
- [x] 1.2 Time Bifrost's `/openai/v1/models` per provider and confirm the
      `x-bf-list-models-provider` header is ignored — every provider returns the
      identical full cross-provider listing in ~6.5s.
- [x] 1.3 Reproduce in a throwaway Bifrost container with zero API keys to prove
      keyless providers fail instantly and `lmstudio` retry backoff owns the
      ~7s, then confirm the tightened retry policy returns in ~0.22s.

## 2. Dashboard renders without the catalog

- [x] 2.1 Start `listProviders()` outside the blocking `Promise.allSettled` in
      `usePlaySessionLoader`, folding a rejection into `null` so it can never
      become an unhandled rejection when the blocking load bails out early.
- [x] 2.2 Seed the draft from `createDefaultDraft(config)` and set status
      `Ready` without waiting for the catalog.
- [x] 2.3 Apply the catalog when it resolves: set providers, re-seed the
      provider/model selectors via `pickDefaultProviderModel`, and update the
      unavailable-provider notice.
- [x] 2.4 Guard the re-seed so it never overwrites a draft the user edited or
      one a loaded session committed (`committedModelRef`).

## 3. Gateway fails fast on an absent LM Studio

- [x] 3.1 Tighten the `lmstudio` `network_config` retry policy in
      `services/bifrost/config.json` to `max_retries: 1`,
      `retry_backoff_initial: 200`, `retry_backoff_max: 1000`.

## 4. Tests

- [x] 4.1 Dashboard test: the workspace renders and reports `Ready` while
      `/providers` is still in flight, then picks up the catalog when it lands.
- [x] 4.2 Dashboard test: once the catalog arrives the selectors default to a
      working provider and the unavailable provider is surfaced as a notice.
- [x] 4.3 `./scripts/lint.sh --fix` and `./scripts/test.sh unit` pass.
