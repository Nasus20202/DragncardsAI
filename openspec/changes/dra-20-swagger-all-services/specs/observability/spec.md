## MODIFIED Requirements

### Requirement: HTTP and runtime edges are instrumented across first-party services
The system SHALL instrument the highest-value request and runtime boundaries in each
first-party service so developers can inspect latency and failures across inter-service
flows.

The dashboard's set of trace-context propagation targets SHALL be derived from the single
declaration of the services the dashboard fronts, not written out as its own list of
service names. A hand-written list is what made history-service and eval-service invisible
in dashboard-initiated traces, and a test that hardcodes the same names cannot detect the
omission it is meant to prevent.

#### Scenario: Python HTTP servers emit request telemetry
- **WHEN** `game-service`, `agent-orchestrator`, `history-service` or `eval-service` handles an HTTP request
- **THEN** the service SHALL emit trace and metric data for that request including route-level attribution and response outcome

#### Scenario: Python HTTP server auto-instrumentation exports core request metrics
- **WHEN** `game-service`, `agent-orchestrator`, `history-service` or `eval-service` handles HTTP traffic with telemetry enabled
- **THEN** the observability stack SHALL receive the `http_server_duration_milliseconds`, `http_server_active_requests`, and `http_server_response_size_bytes` metric families for that service

#### Scenario: Dashboard server emits server-side request telemetry
- **WHEN** `dashboard` handles a server-side route or proxy request
- **THEN** it SHALL emit server-side telemetry for that request and any upstream call it performs to first-party backend services

#### Scenario: Dashboard propagates trace context to every first-party backend
- **WHEN** `dashboard` performs a server-side call to `game-service`, `agent-orchestrator`, `history-service` or `eval-service`, by Docker service name or by the host of its configured base URL
- **THEN** it SHALL propagate trace context on that call, so the backend's spans join the dashboard's trace as children instead of starting a separate trace
- **AND** the set of propagation targets SHALL be derived from the declared set of services the dashboard fronts, so a service added to that declaration is covered without a second list to update
- **AND** the set of propagation targets SHALL be asserted by a test driven by that same declaration, so adding a backend without covering it is caught rather than silently producing disconnected traces

#### Scenario: Propagation follows the configured upstream, not a fixed hostname
- **WHEN** a first-party backend's base URL is configured to a host other than the local default
- **THEN** the dashboard SHALL propagate trace context to that configured host as well as to the service's Docker service name
