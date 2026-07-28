# Support a dedicated judge key for any Bifrost provider

## Why

The user asked whether the judge API key can be configured like any normal model
API key — specifically, whether they can judge with OpenRouter rather than only
Anthropic. Investigating the answer turned up a live bug: **the dedicated judge
identity never worked at all, for any provider, including Anthropic.**

Two independent mistakes combined.

### 1. The `Authorization` bearer does not select a provider key

`services/eval-service` sent its `BIFROST_API_KEY` as `Authorization: Bearer …`,
documented as "the `eval-judge` virtual key". Bifrost does not treat that header
as a key selector. Verified empirically against `maximhq/bifrost:v1.6.6` with a
throwaway gateway whose upstream echoed back the credential it received:

| Request | Upstream credential used |
| --- | --- |
| no auth header | the game-playing key |
| `Authorization: Bearer eval-judge` | the game-playing key |
| `Authorization: Bearer <the judge key's raw value>` | the game-playing key |
| `x-bf-api-key: eval-judge` | **the judge key** |

The gateway's own `/api/config` explains why: `enforce_auth_on_inference: false`
(so no gateway auth is required or consumed), `allow_direct_keys: false` (so a
raw provider key in the bearer is not honoured), and
`/api/governance/virtual-keys` returns `count: 0` — there were no virtual keys to
match. The bearer was inert. The real mechanism is the `x-bf-api-key` header,
which names a key entry of whichever provider the model id routes to.

### 2. `weight: 0.0` means "never auto-selected", not "reserved"

`services/bifrost/config.json` defined the `eval-judge` key at `weight: 0.0`
under `anthropic` only. Without explicit selection, Bifrost picks a key by
weighted random choice over the provider's keys, and a `0.0` weight is chosen
never: 20 consecutive unheadered calls all drew the game-playing key. So the
judge key sat unreachable. Explicit `x-bf-api-key` selection overrides the
weight, which is what makes `0.0` the right value once selection is wired up.

Compounding this, `EVAL_JUDGE_API_KEY` was unset in the operator's environment,
and Bifrost treats a key whose `env.` reference is unset as absent.

### What would have happened with `EVAL_JUDGE_PROVIDER=openrouter`

The judge call would have **succeeded, silently billed to `OPENROUTER_API_KEY`**
— the game-playing key. Verified directly: a judge request to a provider with no
`eval-judge` entry, carrying `Authorization: Bearer eval-judge`, reached the
upstream under the gameplay credential. No error, no warning, no separate budget.
That is the exact failure the `infrastructure` spec's "Dedicated Bifrost judge
identity" requirement exists to prevent, and the same silent reuse was happening
for Anthropic too.

## What Changes

- **Judge key per provider.** Every provider in `services/bifrost/config.json`
  (`openai`, `anthropic`, `gemini`, `mistral`, `openrouter`, `nvidia`,
  `lmstudio`) now carries a second key entry named `eval-judge` at
  `"weight": 0.0`, each sourced from its own non-committed env reference
  `env.EVAL_JUDGE_<PROVIDER>_API_KEY`. `lmstudio` uses the same `dummy` value as
  its gameplay key, being a keyless local server.
- **The eval-service pins the judge identity by name.** New
  `EVAL_JUDGE_BIFROST_KEY_NAME` (default `eval-judge`) is sent as
  `x-bf-api-key` on every judge call and stream. Because Bifrost resolves the
  name against the *target* provider's keys, one setting covers every provider —
  `EVAL_JUDGE_MODEL=openrouter/anthropic/claude-sonnet-4` now draws
  `EVAL_JUDGE_OPENROUTER_API_KEY`. Verified end-to-end through the real
  `BifrostJudgeClient` against a live gateway.
- **`EVAL_JUDGE_API_KEY` is renamed** to `EVAL_JUDGE_ANTHROPIC_API_KEY` for a
  uniform per-provider convention. Nothing regresses: the old variable was never
  reachable by judge traffic.
- **Misconfiguration is loud.** Three layers, none of which is a silent fallback:
  - `GET /ready` gains `judge_key: {name, provider, status, providers}` and
    reports `degraded` when `status` is `missing`. `providers` lists which
    providers do have a judge key. `status` is `unknown` when Bifrost's key
    listing is unreadable (which does not degrade on its own — the existing
    `bifrost` check already covers reachability) and `disabled` for the
    deliberate opt-out.
  - Bifrost itself rejects a judge call to a provider with no such key:
    `no supported key found with name "eval-judge" for provider: <p>`, HTTP 400.
    Being a definitive 4xx it is not retried.
  - That gateway message is now recorded as the target's skip reason. Previously
    every judge failure collapsed to the generic
    `judge failed after retry limit`, which would have hidden the cause entirely.
- **Falling back to the game-playing key stays possible but explicit.** Setting
  `EVAL_JUDGE_BIFROST_KEY_NAME=""` opts out; it is warned at startup and shown as
  `judge_key.status: disabled` in readiness.
- **Docs corrected.** `services/eval-service/README.md` gains a "Judge identity"
  section covering the mechanism, how to add a judge key for another provider,
  and how misconfiguration surfaces. `AGENTS.md`, both `.env.example` files, and
  the compose comments no longer describe the bearer as the judge's virtual key.

## Non-goals

- **Bifrost governance virtual keys.** A real virtual key with a budget
  (`/api/governance/virtual-keys`) would also satisfy the spec, but it requires
  `enforce_auth_on_inference: true`, which would mean issuing and distributing
  gateway credentials to every service — a much larger change to local
  development for no gain over per-provider named keys.
- **Dashboard changes.** `features/history/components/judge-config.tsx` lists
  judge providers from the orchestrator's provider list. Every shipped provider
  now has an `eval-judge` entry, so that list is already accurate about which
  providers can judge; whether an operator populated a given secret is not
  visible in Bifrost's key listing (env-referenced entries always report an empty
  value), so the UI could not report it faithfully. The operator signal lives in
  `/ready` and the per-target error instead.
- **Verifying that a judge key's secret is non-empty.** Bifrost's key listing
  reports env-referenced values as empty whether or not the variable is set, so
  readiness checks that the *entry* exists. An unpopulated secret is caught at
  judge time by the same explicit 400.
- **Per-provider judge budgets inside Bifrost.** Budgets/rate limits are a
  governance-plugin feature; this change gives the judge a distinct, attributable
  credential per provider, which is what the spec requires.

## Impact

- Affected specs: `infrastructure`, `agent-move-evaluation`.
- Affected files: `services/bifrost/config.json`, `services/bifrost/.env.example`,
  `docker-compose.yaml`, `services/eval-service/src/eval_service/config.py`,
  `services/eval-service/src/eval_service/integrations/bifrost.py`,
  `services/eval-service/src/eval_service/judge/config.py`,
  `services/eval-service/src/eval_service/api/routers/meta.py`,
  `services/eval-service/src/eval_service/runtime/app.py`,
  `services/eval-service/src/eval_service/runtime/evaluator.py`,
  `services/eval-service/{README,AGENTS}.md`, `services/eval-service/.env.example`,
  and the eval-service unit tests.
- **Operator action required.** Set `EVAL_JUDGE_<PROVIDER>_API_KEY` in
  `services/bifrost/.env` for the provider(s) you judge with, then restart
  Bifrost so it re-reads `config.json` and the environment. Until then, judge
  calls to that provider fail with the explicit gateway error — which is the
  intended behaviour, replacing the previous silent spend on the gameplay key.
- No database schema or HTTP request/response contract changes; `/ready` gains a
  field.
