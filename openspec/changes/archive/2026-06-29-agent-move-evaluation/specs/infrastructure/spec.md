## ADDED Requirements

### Requirement: Eval Service Docker configuration
The infrastructure compose configuration SHALL define an `eval-service` and its dedicated PostgreSQL database with secret-free defaults, isolated from the history-service and agent-orchestrator databases.

#### Scenario: Eval-service and its database start
- **WHEN** `docker compose up` is run
- **THEN** the `eval-service` and its dedicated PostgreSQL service SHALL start and provide storage used only by the eval-service

#### Scenario: Eval database is isolated
- **WHEN** compose configuration is inspected
- **THEN** the eval-service SHALL connect to its own dedicated PostgreSQL service rather than the history-service, agent-orchestrator, or any other shared database service

### Requirement: Dedicated Bifrost judge identity
The infrastructure Bifrost gateway configuration SHALL define a dedicated judge virtual key/provider entry for evaluation traffic, separate from the game-playing provider keys, configured through non-committed runtime secrets so the judge has its own budget and recognizable identity.

#### Scenario: Dedicated judge key present in Bifrost configuration
- **WHEN** the Bifrost gateway configuration is inspected
- **THEN** a dedicated judge virtual key/provider entry SHALL be present, distinct from the game-playing keys, and the eval-service SHALL route judge traffic under it

#### Scenario: Judge key secret remains external
- **WHEN** repository files are inspected
- **THEN** the judge identity's API key or access token SHALL NOT be committed in compose files, default env files, tests, or source code
