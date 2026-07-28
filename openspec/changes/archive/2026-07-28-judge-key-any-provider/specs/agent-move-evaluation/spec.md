## MODIFIED Requirements

### Requirement: Isolated judge LLM under a dedicated Bifrost identity

The eval-service SHALL run each evaluation through a fresh, stateless judge LLM invocation routed through the Bifrost gateway under a dedicated judge key that is separate from the game-playing keys, for WHICHEVER provider the configured judge model routes to. The judge model and provider SHALL be operator-configured with NO built-in default; the eval-service SHALL refuse to perform an evaluation when no judge model is configured. The judge SHALL NOT reuse or mutate the game-playing agent's session.

The eval-service SHALL address the judge key by an operator-configurable NAME, sent as the gateway's named-key selection header, so a single setting pins the judge identity across every provider. The eval-service SHALL NOT rely on the gateway authorization bearer to select a provider key. Judge traffic SHALL NOT fall back to a game-playing key implicitly; where an operator deliberately disables named-key selection, the service SHALL log that at startup and report it in readiness.

#### Scenario: Judge runs in a fresh isolated session
- **WHEN** the eval-service invokes the judge for a target
- **THEN** the judge invocation SHALL be a fresh session containing only the evaluation prompt and assembled inputs and SHALL NOT reuse the game-playing agent's session or context

#### Scenario: Judge traffic uses the dedicated Bifrost identity
- **WHEN** the eval-service sends a judge request through Bifrost
- **THEN** the request SHALL name the dedicated judge key so the gateway selects it for the target provider, and SHALL NOT use a game-playing identity

#### Scenario: Judge identity holds for any provider
- **WHEN** the configured judge model routes to a provider other than the default one
- **THEN** the same named judge key SHALL be selected for that provider, so the judge uses that provider's own judge credential rather than its game-playing key, with no code change

#### Scenario: Judge model and provider are configurable
- **WHEN** an operator configures the eval-service judge model and provider
- **THEN** the eval-service SHALL route judge requests to that configured model and provider through Bifrost without code changes

#### Scenario: No judge model configured
- **WHEN** the eval-service is asked to evaluate a target but no judge model has been configured
- **THEN** the eval-service SHALL NOT invoke a default model and SHALL skip the evaluation with a clear configuration error rather than guessing a model

#### Scenario: Missing judge key is reported, not absorbed
- **WHEN** the judge provider has no dedicated judge key configured
- **THEN** readiness SHALL report the judge key as missing for that provider and SHALL report status `degraded`
- **AND** an attempted evaluation SHALL be recorded against the target with the gateway's own error identifying the missing key and provider, rather than a generic judge failure

### Requirement: Evaluation service boundary and persistence

The system SHALL provide a dedicated `eval-service` (Python/FastAPI) that evaluates how well the game-playing agent played by judging recorded moves and rounds on user request, and SHALL NOT retain evaluation state in process memory; durable evaluation requests, idempotency, and bookkeeping data SHALL live in a dedicated PostgreSQL database not shared with other services.

The eval-service container image SHALL start cleanly regardless of the module's on-disk depth, and SHALL package the shared rules-skill directory so that skill names selected for a judge configuration resolve to skill content inside the container.

#### Scenario: Eval-service uses dedicated isolated storage
- **WHEN** the eval-service records that a target has been evaluated
- **THEN** the eval-service SHALL persist that record in its dedicated PostgreSQL database and SHALL NOT keep evaluation bookkeeping only in process memory

#### Scenario: Health and readiness without secrets
- **WHEN** a client requests the eval-service health or readiness endpoint
- **THEN** the eval-service SHALL report API, PostgreSQL, history-service, and Bifrost readiness, plus whether a judge model and a dedicated judge key for its provider are configured, and SHALL NOT expose any secret values

#### Scenario: Packaged service boots and resolves skills
- **WHEN** the eval-service container image starts
- **THEN** the service SHALL boot to a healthy state without an import-time error, and SHALL resolve rules-skill names against a skills directory packaged into the image at the configured skill root
