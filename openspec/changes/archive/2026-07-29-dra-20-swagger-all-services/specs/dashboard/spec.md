## MODIFIED Requirements

### Requirement: Merged Swagger playground
The dashboard SHALL provide a Swagger section that displays a merged OpenAPI document for
**every** first-party service it proxies — agent-orchestrator, game-service, history-service and
eval-service — and routes playground calls through dashboard proxy routes.

The set of services the merged document covers SHALL be derived from the same single declaration
that determines which services the proxy route accepts, so a service cannot be reachable through
the proxy while being absent from the index. The merge SHALL NOT iterate a separate literal list
of service names.

Each service's document SHALL be fetched from that service's own configured base URL and its own
configured OpenAPI source path. Resolution SHALL be exhaustive over the declared service set, so
a declared service without a configured base URL or OpenAPI path is a build-time failure rather
than a request that silently retrieves another service's document.

Merged endpoints SHALL be namespaced per service — path prefix, operation ids, tags, and
component names — so two services publishing the same path or schema name cannot collide, and
the path prefix SHALL be the same service segment the proxy route accepts.

#### Scenario: Every proxied service appears in the merged document
- **WHEN** a user opens the Swagger section
- **THEN** the dashboard SHALL fetch or serve a merged OpenAPI document containing the endpoints
  of every service the dashboard proxies, each under that service's own path prefix

#### Scenario: A newly declared service is covered without editing the merge
- **WHEN** a service is added to the single declaration of services the dashboard fronts
- **THEN** the merged OpenAPI document SHALL include that service's endpoints once its base URL
  and OpenAPI source path are configured, without any change to the merging logic itself

#### Scenario: Each service is read from its own upstream
- **WHEN** the dashboard fetches the upstream OpenAPI documents
- **THEN** it SHALL request each service's document from that service's configured base URL and
  OpenAPI source path
- **AND** SHALL NOT resolve one service's document against another service's base URL or path

#### Scenario: Proxy playground request
- **WHEN** a user executes an API request from the Swagger playground
- **THEN** the dashboard SHALL proxy the request to the matching upstream service and return the
  upstream response to the playground

#### Scenario: Upstream spec unavailable
- **WHEN** one configured service OpenAPI document cannot be fetched
- **THEN** the dashboard SHALL still report the error clearly, naming the service that failed,
  and SHALL render the available service specs

### Requirement: Dashboard service configuration
The dashboard SHALL use non-secret environment configuration for service base URLs, OpenAPI
source paths, and default session settings. Every service the dashboard proxies SHALL have both a
base URL and an OpenAPI source path available from that configuration, each overridable by its own
environment variable and each defaulting to the value that works against the local stack.

#### Scenario: Load service endpoints from environment
- **WHEN** the dashboard starts
- **THEN** it SHALL read the base URL of every service it proxies from environment-backed
  configuration

#### Scenario: Per-service OpenAPI source path override
- **WHEN** a service serves its OpenAPI document somewhere other than the default path and the
  corresponding environment variable is set
- **THEN** the dashboard SHALL fetch that service's document from the overridden path and leave
  the other services' paths unchanged

#### Scenario: Missing required service configuration
- **WHEN** required dashboard service URLs are missing
- **THEN** the dashboard SHALL show a clear configuration error instead of silently sending
  requests to an invalid target
