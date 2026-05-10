# Agent Orchestrator Spec

## Purpose

This spec describes the agent orchestration service for DragnCardsAI, including session management, background prompt execution, provider integration through Bifrost, MCP tool usage, and streaming job events.

## Requirements

### Requirement: Agent session lifecycle API
The system SHALL expose HTTP endpoints to create, retrieve, list, update, and terminate agent sessions used to run LLM-driven DragnCards gameplay.

#### Scenario: Create agent session
- **WHEN** a client submits a valid request to create an agent session
- **THEN** the system SHALL persist the session and return its identifier, lifecycle status, and configuration summary

#### Scenario: Retrieve agent session
- **WHEN** a client requests an existing agent session by identifier
- **THEN** the system SHALL return the persisted session state, model configuration, assigned skills, assigned MCPs, and recent job summary

#### Scenario: Terminate agent session
- **WHEN** a client terminates an active agent session
- **THEN** the system SHALL mark the session terminated and prevent new prompt jobs from being accepted for that session

### Requirement: Model and provider configuration
The system SHALL allow each agent session to configure the model provider, model name, gateway options, and provider-specific non-secret settings used for prompt execution.

#### Scenario: Configure supported provider
- **WHEN** a client configures a session with one of OpenRouter, Mistral, Claude, OpenAI, LM Studio, or Gemini
- **THEN** the system SHALL persist the provider configuration and validate that the provider is known to the Bifrost gateway configuration

#### Scenario: Reject unsupported provider
- **WHEN** a client configures a session with an unknown provider identifier
- **THEN** the system SHALL reject the request with a validation error and SHALL NOT change the session model configuration

### Requirement: Skill assignment
The system SHALL allow clients to assign and remove skills from `@skills/` for an agent session, discovered from environment-configured skill roots using the directory shape `skills/<skill_name>`.

#### Scenario: Assign known skill
- **WHEN** a client assigns a skill identifier that exists under `skills/<skill_name>` in a configured skill root
- **THEN** the system SHALL persist the skill assignment for the session

#### Scenario: Reject unknown skill
- **WHEN** a client assigns a skill identifier that cannot be resolved from configured skill roots
- **THEN** the system SHALL reject the assignment and SHALL NOT persist it

### Requirement: MCP assignment
The system SHALL allow clients to assign and remove MCP server/tool configurations for an agent session, including the game-service MCP.

#### Scenario: Assign game-service MCP
- **WHEN** a client assigns the game-service MCP to an agent session
- **THEN** prompt jobs for that session SHALL be able to call the assigned game-service MCP tools during orchestration

#### Scenario: Inspect MCP assignments
- **WHEN** a client retrieves an agent session
- **THEN** the response SHALL include the MCP assignments available to prompt jobs for that session

### Requirement: Prompt submission creates background jobs
The system SHALL expose an endpoint to submit prompts to an agent session and SHALL execute the resulting orchestration work only through background jobs.

#### Scenario: Submit prompt
- **WHEN** a client submits a prompt to an active agent session
- **THEN** the system SHALL persist a prompt run, enqueue a background job, and return the job identifier without waiting for LLM execution to complete

#### Scenario: Reject prompt for terminated session
- **WHEN** a client submits a prompt to a terminated agent session
- **THEN** the system SHALL reject the prompt and SHALL NOT enqueue a job

### Requirement: Persistent orchestration jobs
The system SHALL persist job lifecycle state, attempts, timestamps, errors, prompt inputs, generated outputs, and tool interaction events in a dedicated agent-orchestrator PostgreSQL database that is not shared with other services.

#### Scenario: Job completes
- **WHEN** a background worker completes a prompt job successfully
- **THEN** the system SHALL persist the completed status, final output, completion timestamp, and related orchestration events

#### Scenario: Dedicated database isolation
- **WHEN** the orchestrator is configured for persistence
- **THEN** it SHALL connect to its own PostgreSQL database instance or database name reserved for orchestrator data and SHALL NOT write orchestration tables into databases used by DragnCards or other services

#### Scenario: Job fails
- **WHEN** a background worker fails a prompt job
- **THEN** the system SHALL persist the failed status, error details, completion timestamp, and any events produced before failure

#### Scenario: Job is cancelled
- **WHEN** a client requests cancellation for a queued or running job
- **THEN** the system SHALL persist the cancellation request and the worker SHALL stop the job before any further model or MCP calls when cancellation is observed

### Requirement: Bifrost gateway execution
The system SHALL route LLM prompt execution through Bifrost rather than calling provider SDKs directly.

#### Scenario: Execute through configured gateway
- **WHEN** a worker executes a prompt job for a configured session
- **THEN** the worker SHALL call Bifrost using the session provider and model configuration

#### Scenario: Gateway failure is recorded
- **WHEN** Bifrost returns an error during prompt execution
- **THEN** the system SHALL record the gateway error on the job and mark the job failed unless retry policy allows another attempt

### Requirement: Streaming event API
The system SHALL expose a streaming-compatible API for clients to consume session and job events produced during orchestration.

#### Scenario: Stream job events
- **WHEN** a client subscribes to the event stream for a job
- **THEN** the system SHALL emit persisted events for prompt progress, model output chunks, tool calls, tool results, completion, failure, and cancellation as they become available

#### Scenario: Resume event stream
- **WHEN** a client reconnects with a last-seen event cursor
- **THEN** the system SHALL resume streaming from events after that cursor

### Requirement: Dashboard-readable session metadata
The agent-orchestrator SHALL expose enough session metadata for a dashboard client to list, select, inspect, and configure sessions without relying on internal storage details.

#### Scenario: Dashboard lists session summaries
- **WHEN** the dashboard requests agent sessions
- **THEN** the agent-orchestrator SHALL return session identifiers, lifecycle status, model/provider summary, assigned MCPs, assigned skills, and recent job summary suitable for display

#### Scenario: Dashboard retrieves session details
- **WHEN** the dashboard requests one agent session
- **THEN** the agent-orchestrator SHALL return the session configuration, assigned MCPs, assigned skills, lifecycle status, and recent orchestration job state

### Requirement: Dashboard session defaults contract
The agent-orchestrator SHALL accept session creation and update requests that include dashboard-provided default model/provider settings, skill assignments, and MCP assignments.

#### Scenario: Create session from dashboard defaults
- **WHEN** the dashboard creates a session with default model/provider, skills, and MCPs
- **THEN** the agent-orchestrator SHALL validate and persist those settings using the same rules as other session creation clients

#### Scenario: Reject invalid dashboard defaults
- **WHEN** the dashboard submits an unknown provider, skill, or MCP assignment
- **THEN** the agent-orchestrator SHALL reject the invalid value with a descriptive validation error and SHALL NOT partially persist the rejected assignment

### Requirement: Dashboard event stream compatibility
The agent-orchestrator SHALL expose streaming job events in a form that allows dashboard clients to render live chat output, progress summaries, tool calls, tool results, errors, and completion state.

#### Scenario: Stream dashboard event types
- **WHEN** a prompt job emits orchestration events
- **THEN** the agent-orchestrator SHALL provide event type, event identifier or cursor, timestamp, job identifier, and payload fields sufficient for the dashboard to render the event

#### Scenario: Resume dashboard event stream
- **WHEN** the dashboard reconnects with a last-seen event cursor
- **THEN** the agent-orchestrator SHALL stream only events after that cursor

### Requirement: Incremental streaming event persistence
The agent-orchestrator SHALL write streaming model output and reasoning events to the database incrementally during generation so that reconnecting clients can recover partial output without losing in-flight content.

#### Scenario: First chunk creates DB row
- **WHEN** the first model output or reasoning chunk arrives during streaming
- **THEN** the worker SHALL persist a DB event row immediately via append_event, capturing the initial partial text

#### Scenario: Subsequent chunks update DB row
- **WHEN** additional model output or reasoning chunks arrive
- **THEN** the worker SHALL update the existing DB row via update_event at regular intervals so the snapshot reflects accumulated text

#### Scenario: Reconnecting client receives partial output
- **WHEN** a client reconnects mid-stream after disconnecting
- **THEN** the event stream SHALL replay the latest DB snapshot of in-progress events so the client sees partial output without waiting for the stream to complete

### Requirement: Live event bus replay for late subscribers
The agent-orchestrator live event bus SHALL buffer recent events per job and deliver them to late subscribers so that clients reconnecting during active streaming do not miss events published between disconnect and reconnect.

#### Scenario: Late subscriber catches up
- **WHEN** a client subscribes to the live event bus after events have already been published for a job
- **THEN** the subscriber SHALL receive all buffered events up to the replay buffer limit before receiving new events

#### Scenario: Buffer evicts oldest events
- **WHEN** the number of buffered events for a job exceeds the configured replay buffer size
- **THEN** the oldest events SHALL be evicted and only the most recent events SHALL be replayed to new subscribers

#### Scenario: Subscriber cleanup on disconnect
- **WHEN** a subscriber closes its connection
- **THEN** the bus SHALL remove the subscriber from its active queue set and SHALL NOT deliver further events to it

### Requirement: Agent orchestrator OpenAPI availability
The agent-orchestrator SHALL expose an OpenAPI document suitable for dashboard aggregation.

#### Scenario: Fetch orchestrator OpenAPI
- **WHEN** the dashboard requests the agent-orchestrator OpenAPI document from the configured endpoint
- **THEN** the agent-orchestrator SHALL return a valid OpenAPI document for its HTTP API

### Requirement: Provider secrets are externalized
The system SHALL read provider credentials and gateway secrets from environment or local runtime configuration and SHALL NOT require secrets to be committed to the repository.

#### Scenario: Missing provider secret
- **WHEN** a worker attempts to execute a job for a provider without required runtime credentials
- **THEN** the system SHALL fail the job with a configuration error that does not expose secret values

### Requirement: Orchestrator health and readiness
The system SHALL expose health and readiness endpoints for the API, database connectivity, worker availability, and Bifrost connectivity.

#### Scenario: Readiness succeeds
- **WHEN** PostgreSQL is reachable and required orchestrator configuration is valid
- **THEN** the readiness endpoint SHALL report ready

#### Scenario: Readiness fails
- **WHEN** PostgreSQL is unreachable or required orchestrator configuration is invalid
- **THEN** the readiness endpoint SHALL report not ready with non-secret diagnostic details
