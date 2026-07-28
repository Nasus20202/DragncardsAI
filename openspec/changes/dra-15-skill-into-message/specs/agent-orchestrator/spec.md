## ADDED Requirements

### Requirement: A prompt can load skill content into its own turn
The prompt submission endpoint SHALL accept the names of skills whose full content the prompt loads into its own turn, and SHALL record them on the enqueued job so the worker can act on them.

Each named skill SHALL resolve in the configured skill roots; a name that does not SHALL be rejected as a bad request and SHALL NOT enqueue a job. The number of skills one prompt may load SHALL be bounded, and a request exceeding that bound SHALL be rejected as a bad request. Repeated names SHALL be recorded once, in the order first given.

The names the worker acts on SHALL be the validated ones. A client SHALL NOT be able to smuggle unvalidated skill names past this validation through free-form job metadata.

When a job names no skills, prompt submission SHALL behave exactly as before.

#### Scenario: Submit a prompt that loads a skill
- **WHEN** a client submits a prompt naming a skill that resolves in a configured skill root
- **THEN** the system SHALL enqueue the job and record that skill against it

#### Scenario: Reject a prompt naming an unknown skill
- **WHEN** a client submits a prompt naming a skill that cannot be resolved from the configured skill roots
- **THEN** the system SHALL reject the request as a bad request and SHALL NOT enqueue a job

#### Scenario: Reject a prompt loading too many skills
- **WHEN** a client submits a prompt naming more skills than one prompt may load
- **THEN** the system SHALL reject the request as a bad request and SHALL NOT enqueue a job

#### Scenario: Duplicate names collapse
- **WHEN** a client submits a prompt naming the same skill twice
- **THEN** the system SHALL record that skill once

#### Scenario: Metadata cannot forge the loaded skill list
- **WHEN** a client submits a prompt whose free-form metadata carries the key the system uses to record loaded skills
- **THEN** the system SHALL record only the validated names from the request's own skill list

### Requirement: Skills loaded by a prompt are delivered in that turn's user message
When a job records skills loaded by its prompt, the worker SHALL place each skill's full content — `SKILL.md` plus the inventory of its reference files, the same payload the `load_skill` built-in returns — ahead of the user's text inside that turn's user message, and SHALL tell the model those instructions are already present so it does not load them again.

The stored job prompt SHALL remain exactly the text the client submitted. Skill content SHALL NOT be written into it, so the transcript, the session name derived from a first prompt, and the replayed message history are unaffected — a later turn replays the typed text only, and the skill's content occupies context on the turn that loaded it and no other.

A recorded skill that no longer resolves on disk SHALL be skipped rather than failing the job.

For each skill actually loaded this way the worker SHALL record and publish a `skill_loaded` event carrying the skill name and its reference-file count, the same event a `load_skill` call produces, so the transcript shows the load.

The system prompt SHALL be unaffected: it still advertises assigned skills by summary only.

#### Scenario: Loaded skill content precedes the user's text
- **WHEN** a job whose prompt loaded a skill starts
- **THEN** that turn's user message SHALL contain the skill's `SKILL.md` content followed by the text the user submitted

#### Scenario: The stored prompt stays as typed
- **WHEN** a job whose prompt loaded a skill has run
- **THEN** the job's stored prompt SHALL be exactly the submitted text, with no skill content in it

#### Scenario: Loading is not repeated on later turns
- **WHEN** a later job in the same session replays that earlier turn from history
- **THEN** the replayed user message SHALL be the typed text only, without the loaded skill's content

#### Scenario: A load emits a skill_loaded event
- **WHEN** a job's prompt loads a skill
- **THEN** the system SHALL record and publish a `skill_loaded` event naming that skill

#### Scenario: A skill that vanished from disk is skipped
- **WHEN** a job records a skill that no longer resolves in the configured skill roots
- **THEN** the worker SHALL run the turn without that skill's content and SHALL NOT fail the job
