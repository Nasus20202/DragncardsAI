# Durable evaluation evidence metadata

## ADDED Requirements

### Requirement: Agent move evidence preserves coordinator provenance

The history-service SHALL store and return an agent move's additive coordinator provenance unchanged when supplied. Provenance SHALL identify that the prompt came from a coordinator and carry the exact prompt text plus server-set orchestrator, parent-job, and child-job identifiers. The history-service SHALL continue accepting moves that omit the field.

#### Scenario: Coordinator provenance survives durable storage

- **WHEN** an orchestrated player move is ingested with coordinator prompt provenance
- **THEN** the stored and retrieved agent event SHALL preserve the provenance source, prompt, and identifiers without moving them into a generic action field

#### Scenario: Legacy move payload remains valid

- **WHEN** a chat or pre-provenance agent move is ingested without coordinator metadata
- **THEN** the history-service SHALL store and return it unchanged and SHALL not require fabricated provenance

### Requirement: Marvel enumerated option identity is retained as producer data

The history-service SHALL preserve a resolved Marvel enumerated option identity in the agent move payload under `marvel_lcg_option` when supplied by the producer. The object SHALL retain `id`, `name`, and `event` and SHALL not be reconstructed from generic history events, option names alone, or model-authored arguments. Existing payloads without the additive object SHALL remain readable.

#### Scenario: A resolved Marvel option is retrievable by evaluator

- **WHEN** history ingests an agent move carrying `platform=marvel-lcg` and `payload.marvel_lcg_option` with `id`, `name`, and `event`
- **THEN** a later history read SHALL return those fields verbatim for eval-service to use as the move identity


#### Scenario: Top-level listing event metadata is durable

- **WHEN** a producer-confirmed selected option has `id` and `name`, and its successful normalized listing carries `event_name` at the response level
- **THEN** history SHALL preserve `payload.marvel_lcg_option.event` with that response-level value

#### Scenario: History does not invent an option identity

- **WHEN** history ingests a Marvel move with only a generic action name or an incomplete option object
- **THEN** the service SHALL preserve the supplied payload without filling missing option fields from another event
