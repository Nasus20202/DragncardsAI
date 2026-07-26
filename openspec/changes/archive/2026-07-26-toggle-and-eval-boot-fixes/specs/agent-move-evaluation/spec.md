## MODIFIED Requirements

### Requirement: Evaluation service boundary and persistence
The system SHALL provide a dedicated `eval-service` (Python/FastAPI) that evaluates how well the game-playing agent played by judging recorded moves and rounds on user request, and SHALL NOT retain evaluation state in process memory; durable evaluation requests, idempotency, and bookkeeping data SHALL live in a dedicated PostgreSQL database not shared with other services.

The eval-service container image SHALL start cleanly regardless of the module's on-disk depth, and SHALL package the shared rules-skill directory so that skill names selected for a judge configuration resolve to skill content inside the container.

#### Scenario: Eval-service uses dedicated isolated storage
- **WHEN** the eval-service records that a target has been evaluated
- **THEN** the eval-service SHALL persist that record in its dedicated PostgreSQL database and SHALL NOT keep evaluation bookkeeping only in process memory

#### Scenario: Health and readiness without secrets
- **WHEN** a client requests the eval-service health or readiness endpoint
- **THEN** the eval-service SHALL report API, PostgreSQL, history-service, and Bifrost readiness and SHALL NOT expose any secret values

#### Scenario: Packaged service boots and resolves skills
- **WHEN** the eval-service container image starts
- **THEN** the service SHALL boot to a healthy state without an import-time error, and SHALL resolve rules-skill names against a skills directory packaged into the image at the configured skill root
