## ADDED Requirements

### Requirement: Browser CORS allowlist on every first-party HTTP service

`game-service`, `agent-orchestrator`, `history-service` and `eval-service` SHALL
each restrict browser cross-origin access to a configured allowlist of origins, and
SHALL NOT permit all origins with a wildcard.

The allowlist SHALL be configurable per service through an environment variable, so
that no deployment depends on an origin hardcoded for one machine, and SHALL default
to the local dashboard's browser origin. The variable SHALL be declared in the
service's `.env.example` and passed through in `docker-compose.yaml`.

A wildcard allowlist SHALL be regarded as a defect rather than a development
convenience. Docker Compose publishes each of these services on a host port, so a
wildcard allows any web page loaded in a developer's browser to reach the services'
destructive operations cross-origin — deleting a game's whole recorded history,
backfilling forged events into the ordered store, deleting an agent session, or
submitting a prompt that spends the owner's model budget. Those are the same
operations the MCP surface deliberately withholds from a model, so a wildcard makes
that exclusion decorative.

Restricting origins SHALL NOT be treated as authentication. It constrains browsers
only, for the methods that require a preflight; a non-browser client sends no
`Origin` header and is unaffected. Requiring a credential is a separate concern and
is not satisfied by this requirement.

#### Scenario: A foreign origin is refused a destructive preflight

- **WHEN** a browser on an origin outside a service's allowlist sends a CORS
  preflight requesting a destructive method — for example `DELETE` on
  history-service's `/games/{game_id}`, `POST` on its `/games/{game_id}/events` or
  `/import`, `DELETE` on game-service's `/games/{session_id}`, or `DELETE` on the
  orchestrator's `/sessions/{session_id}`
- **THEN** the service SHALL refuse the preflight and SHALL NOT return an
  `Access-Control-Allow-Origin` header, so that the browser never sends the request
  it was asking permission for

#### Scenario: A foreign origin cannot read a response

- **WHEN** a browser on an origin outside a service's allowlist makes a
  cross-origin request the browser sends without a preflight
- **THEN** the response SHALL carry no `Access-Control-Allow-Origin` header, so the
  calling page cannot read the response body

#### Scenario: The dashboard's origin is granted access explicitly

- **WHEN** a browser on an allowlisted origin sends a CORS preflight to any of the
  four services
- **THEN** the service SHALL grant it and SHALL return `Access-Control-Allow-Origin`
  set to that specific origin rather than to a wildcard

#### Scenario: A request carrying no Origin is unaffected

- **WHEN** a caller that sends no `Origin` header reaches any of the four services —
  the dashboard's own server-side proxy, another backend service, an MCP client, or
  a command-line tool
- **THEN** the request SHALL be served exactly as it would have been without any
  CORS configuration, and the response SHALL carry no CORS headers

#### Scenario: The allowlist is configured from the environment

- **WHEN** a service's CORS environment variable is set to a comma-separated list of
  origins
- **THEN** the service SHALL allow exactly those origins, ignoring surrounding
  whitespace and empty entries
- **AND** when the variable is unset, the service SHALL fall back to the local
  dashboard origin rather than to a wildcard

#### Scenario: The shipped default is pinned by a test

- **WHEN** the unit suite of each of the four services runs
- **THEN** it SHALL assert against the service's real application, over HTTP rather
  than by reading configuration, that a foreign origin is refused a destructive
  preflight, that an allowlisted origin is granted one, and that a request with no
  `Origin` still succeeds
- **AND** an edit that restores a wildcard allowlist, whether by widening the
  configured default or by hardcoding it in the application factory, SHALL fail that
  suite
