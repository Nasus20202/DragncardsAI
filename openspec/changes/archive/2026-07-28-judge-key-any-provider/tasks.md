## 1. Establish the real Bifrost key-selection behaviour

- [x] 1.1 Query the running gateway read-only: `/api/config` shows
      `enforce_auth_on_inference: false` and `allow_direct_keys: false`;
      `/api/governance/virtual-keys` returns `count: 0`. So the
      `Authorization: Bearer` value is neither gateway auth that selects a key,
      nor a direct provider key, nor a virtual key.
- [x] 1.2 Run a throwaway `maximhq/bifrost:v1.6.6` on a spare port against an
      upstream that echoes the credential it receives. Confirm: no header, a
      bearer naming the key, and a bearer carrying the key's raw value all draw
      the game-playing key; `x-bf-api-key: <name>` draws the named key and
      overrides `weight: 0.0`.
- [x] 1.3 Confirm `weight: 0.0` is never auto-selected (20/20 unheadered calls
      drew the gameplay key) and that a provider with no such key returns
      HTTP 400 `no supported key found with name "…" for provider: …`.
- [x] 1.4 Confirm a key entry whose `env.` reference is unset behaves as absent
      (same 400), so an unpopulated secret can never silently fall through to the
      gameplay key.
- [x] 1.5 Cross-check against Bifrost's documentation that `x-bf-api-key`
      (name) / `x-bf-api-key-id` (id) is the supported selection mechanism.

## 2. Give every provider a judge key

- [x] 2.1 Add an `eval-judge` key entry at `"weight": 0.0` to every provider in
      `services/bifrost/config.json`, each sourced from
      `env.EVAL_JUDGE_<PROVIDER>_API_KEY` (`dummy` for the keyless `lmstudio`).
- [x] 2.2 Rename `EVAL_JUDGE_API_KEY` to `EVAL_JUDGE_ANTHROPIC_API_KEY` and list
      every judge variable in `services/bifrost/.env.example`, documenting the
      convention for adding one for a new provider. Values stay empty.

## 3. Pin judge traffic to the named key

- [x] 3.1 Add `EVAL_JUDGE_BIFROST_KEY_NAME` (default `eval-judge`) to
      `Settings`, plus a `judge_routing_provider` property that derives the
      provider from the model id prefix (which is what Bifrost routes on) and
      falls back to `EVAL_JUDGE_PROVIDER`.
- [x] 3.2 Move `provider_from_model` to `eval_service.config` (re-exported from
      `judge.config`) so `Settings` can use it without a circular import.
- [x] 3.3 Send `x-bf-api-key` from `BifrostJudgeClient` on both the buffered and
      streaming judge paths; omit it when the name is empty.
- [x] 3.4 Wire the setting through `create_app` and pass it through compose.

## 4. Make misconfiguration loud

- [x] 4.1 Add `BifrostJudgeClient.named_key_providers`, reading Bifrost's key
      listing (names + providers only, never a secret) and returning `None` when
      the listing is unreadable so "cannot tell" stays distinct from "missing".
- [x] 4.2 Report `judge_key: {name, provider, status, providers}` from `/ready`
      and degrade on `missing`, following the existing `judge_configured`
      pattern. Do not degrade on `unknown`.
- [x] 4.3 Warn at startup when key selection is deliberately disabled.
- [x] 4.4 Raise `JudgeAttemptsExhaustedError` carrying the last gateway message
      so the target's skip reason names the actual cause instead of the generic
      `judge failed after retry limit`.

## 5. Tests, docs, verification

- [x] 5.1 Unit tests: default and override of the key name; provider derivation
      from the model id; the header is sent, is provider-agnostic, and is omitted
      when opted out; `named_key_providers` parses and degrades safely; the
      missing-key 400 is non-retryable; readiness reports
      present/missing/unknown/disabled and degrades only on `missing`; the
      gateway message reaches the skip reason.
- [x] 5.2 Confirm no secret is echoed by `/ready` by asserting the configured
      gateway token is absent from the response body.
- [x] 5.3 Document the mechanism, the per-provider variables, how to add a
      provider, and how misconfiguration surfaces in
      `services/eval-service/README.md`, `AGENTS.md`, both `.env.example` files,
      and the compose comments.
- [x] 5.4 Verify end-to-end through the real `BifrostJudgeClient` against a live
      gateway: `openai` and `openrouter` judge calls each draw their own judge
      key, unheadered calls draw the gameplay key, and a provider without a judge
      key raises a non-retryable `BifrostError`.
- [x] 5.5 `./scripts/lint.sh --fix`, `./scripts/test.sh unit`, and
      `openspec validate --all`.
