## ADDED Requirements

### Requirement: Generated display names are deterministic and stored
The orchestrator SHALL derive a display name for an agent from two halves: a codename chosen by hashing a seed, and a topic taken from the prompt the agent was given. The codename SHALL be one adjective and one animal drawn from fixed word lists, so that agents seeded differently are told apart at a glance. The topic SHALL be the prompt's content words, so that the name says what the agent was asked to do. A name with no usable topic SHALL be the codename alone.

Name generation SHALL be a pure function of its inputs. The same seed and the same prompt SHALL always produce the same name, and generating a name SHALL NOT call a language model, read the clock, or consult any random source.

A generated name SHALL be stored — on the session it names, and in every event payload that mentions it — and readers SHALL use the stored name rather than recomputing it. A generated name SHALL be bounded in length so that it fits the column that stores it and the controls that display it.

The topic SHALL be built only from text that reads as words. The orchestrator SHALL split the prompt into runs of letters, digits and underscores, and SHALL reject such a run entirely unless every underscore-separated part of it is alphabetic and is all lower case, all upper case, or capitalised. Identifiers, numbers and mixed-case opaque strings SHALL therefore contribute nothing to a name, so that a prompt carrying a credential cannot donate a fragment of it to a name that is stored and displayed. Function words and the orchestrator's own instruction boilerplate SHALL be excluded from the topic, and a word SHALL appear in a topic at most once.

#### Scenario: The same inputs always produce the same name
- **WHEN** a name is generated twice from one seed and one prompt
- **THEN** the two names SHALL be identical
- **AND** generating them SHALL NOT have called a language model

#### Scenario: Different seeds are told apart
- **WHEN** names are generated from many different seeds
- **THEN** the codenames SHALL differ across substantially all of them

#### Scenario: Two identical prompts still get different names
- **WHEN** two agents are seeded differently and given the same prompt
- **THEN** their names SHALL differ

#### Scenario: The topic comes from the prompt, not its boilerplate
- **WHEN** a prompt opens with instruction boilerplate and then states its task
- **THEN** the name SHALL contain words from the task
- **AND** SHALL NOT contain the boilerplate's own words

#### Scenario: A tool name contributes its words
- **WHEN** a prompt names a tool such as `search_cards_marvel_champions`
- **THEN** the name SHALL contain that tool's words

#### Scenario: Identifiers contribute nothing
- **WHEN** a prompt contains a UUID, a card id, a group name such as `player1Play`, or a number
- **THEN** none of them SHALL appear in the generated name

#### Scenario: An opaque letter run is not mined for words
- **WHEN** a prompt contains a credential-shaped mixed-case string
- **THEN** no part of that string SHALL appear in the generated name

#### Scenario: A prompt with no content words still yields a name
- **WHEN** a prompt consists only of function words, or there is no prompt at all
- **THEN** the name SHALL be the codename alone

#### Scenario: A very long prompt yields a bounded name
- **WHEN** a name is generated from a prompt of many thousands of words
- **THEN** the name SHALL be no longer than the generator's documented bound
- **AND** SHALL NOT end part-way through a word

### Requirement: An unnamed session is named from its first prompt
The prompt submission endpoint SHALL give a session a generated name when that session has no name and has no prior job, deriving it from the session's identifier and the prompt being submitted, within the same request that enqueues the job.

A session that already carries a name SHALL NOT be renamed, so a name chosen by whoever created the session is never overwritten. A session that has already run a job SHALL NOT be renamed, so only the first prompt names a session. The name SHALL be persisted, so that every client reads the same name for that session rather than deriving one of its own.

#### Scenario: The first prompt names an unnamed session
- **WHEN** a prompt is submitted to a session that has no name and no prior job
- **THEN** the session SHALL be given a generated name derived from its identifier and that prompt
- **AND** that name SHALL be readable from the session immediately after the request returns

#### Scenario: A later prompt does not rename the session
- **WHEN** a second prompt is submitted to a session that has already run a job
- **THEN** the session's name SHALL be unchanged

#### Scenario: A chosen name is never overwritten
- **WHEN** a prompt is submitted to a session whose creator gave it a name
- **THEN** that name SHALL be unchanged

## MODIFIED Requirements

### Requirement: spawn_subagent creates monitored child jobs without blocking
When the `spawn_subagent` built-in tool is invoked the worker SHALL create a child session, configure it with the parent session's model config and skills, enqueue a prompt job with `parent_job_id` set, give the child session a generated display name, and return a tool result immediately containing the `child_job_id` and that `name`. The child job runs concurrently; the parent agent can continue its work without waiting. A background task SHALL monitor the child job, append the child outcome to the parent job's event log, and terminate the child session when the child reaches a terminal state.

The child's name SHALL be generated rather than taken from the prompt, and SHALL be seeded on the child session's own identifier so that no two children share a codename. The name SHALL be stored on the child session and SHALL be the same string in the `subagent_started` event, in the outcome event the monitor appends, and in the tool result — generated once, never recomputed. A caller that supplies a name for the child SHALL have that name used instead; this is how a player agent keeps its seat's own display name.

`spawn_subagent` SHALL accept an optional persona name. When a persona applies — either because the call named one or because the parent session records a default subagent persona — the child SHALL be configured from the resolved persona instead of from a plain copy of the parent's model config and skills, and the persona SHALL be captured onto the child at that moment. MCP servers SHALL be inherited from the parent either way. When no persona applies the child SHALL be configured exactly as before: a copy of the parent's model config and skill assignments.

The monitor SHALL resolve the child's outcome the same way `wait_for_subagent` does — from the child's persisted status, with live events short-circuiting the wait — so the reported outcome is the child's actual fate and not a timeout observed because no event was ever published. The `reason` on a `subagent_failed` event SHALL be the terminal status the child reached (`failed`, `cancelled`) or why the monitor stopped observing, and SHALL carry the child's `error_code` and `error_message` when it has them. A child that ended `"interrupted"` produced usable partial work and SHALL be reported as `subagent_completed`.

#### Scenario: Child session created and configured
- **WHEN** `spawn_subagent` is called with a valid prompt
- **THEN** the worker SHALL create a new `AgentSession` via the repository
- **THEN** the worker SHALL give the child session a generated name seeded on that session's own identifier
- **THEN** the worker SHALL copy the parent session's model config and skill assignments

#### Scenario: The child's name is generated once and stored
- **WHEN** `spawn_subagent` has started a child
- **THEN** the name on the child session row, the `name` in the `subagent_started` event and the `name` in the tool result SHALL all be the same string
- **AND** that string SHALL NOT be a truncation of the prompt

#### Scenario: A caller-supplied name wins
- **WHEN** a child agent is launched by a caller that supplies its own display name, as a player agent does for its seat
- **THEN** the child session SHALL carry that supplied name and SHALL NOT be given a generated one

#### Scenario: Child job enqueued with parent reference
- **WHEN** the child session is configured
- **THEN** the worker SHALL enqueue a prompt job with `parent_job_id` pointing to the current parent job
- **THEN** the child job SHALL begin running concurrently via `asyncio.create_task`

#### Scenario: spawn_subagent returns immediately
- **WHEN** the child job is enqueued and started
- **THEN** `spawn_subagent` SHALL return a tool result immediately with `child_job_id` and `name` without waiting for the child to finish
- **THEN** the parent agent SHALL continue its own reasoning and may spawn additional subagents

#### Scenario: subagent_started payload includes name
- **WHEN** `spawn_subagent` emits `subagent_started`
- **THEN** the event payload SHALL include `child_job_id`, `child_session_id`, and `name`

#### Scenario: Child configured from a named persona
- **WHEN** `spawn_subagent` is called naming an existing persona
- **THEN** the child session SHALL be configured from that persona's resolved provider, model, options, and skills
- **AND** the `subagent_started` event payload SHALL name the persona the child was started from

#### Scenario: Background task monitors child and emits outcome
- **WHEN** the child job reaches a terminal state
- **THEN** a background coroutine SHALL append `subagent_completed` or `subagent_failed` to the parent job's event log
- **THEN** the background coroutine SHALL terminate the child session

#### Scenario: Monitor reports the child's real failure
- **WHEN** a child job crashes
- **THEN** the `subagent_failed` event on the parent job SHALL carry `reason: "failed"` together with the child's `error_code` and `error_message`
