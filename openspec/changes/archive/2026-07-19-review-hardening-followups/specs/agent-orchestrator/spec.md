## ADDED Requirements

### Requirement: Bounded request body size

The agent-orchestrator SHALL enforce a configurable maximum request body size
ahead of application handling, so that an oversized (or streamed-unbounded)
request body cannot exhaust process memory before per-endpoint validation runs.
A request whose declared `Content-Length` exceeds the limit SHALL be rejected
without buffering the body; a request without a declared length SHALL be
buffered only up to the limit and rejected as soon as the limit is crossed. In
both cases the service SHALL respond with HTTP `413` and SHALL NOT invoke the
route handler. A request within the limit SHALL be processed unchanged.

#### Scenario: Reject a request with an oversized declared Content-Length

- **WHEN** a request arrives whose `Content-Length` header exceeds the configured maximum request body size
- **THEN** the agent-orchestrator SHALL respond with `413` without reading the body and SHALL NOT invoke the route handler

#### Scenario: Reject a streamed body that exceeds the limit

- **WHEN** a request with no declared `Content-Length` streams a body whose total size exceeds the configured maximum
- **THEN** the agent-orchestrator SHALL stop buffering once the limit is crossed and respond with `413` without invoking the route handler

#### Scenario: Process a request within the limit unchanged

- **WHEN** a request body is within the configured maximum
- **THEN** the agent-orchestrator SHALL pass the body to the route handler unchanged
