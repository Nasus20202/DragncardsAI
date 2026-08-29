# State-aware Marvel evaluation

## ADDED Requirements

### Requirement: Marvel move verdicts are checked against authoritative resulting state

For a move recorded on `marvel-lcg`, evaluation SHALL compare the move's authoritative normalized state immediately before and after the move before writing its verdict. The check SHALL read only public normalized fields: terminal `mode` and the current threat token on `zones.sharedMainScheme[0]`. Missing, malformed, raw, or hidden values SHALL remain unavailable and SHALL NOT be fabricated.

#### Scenario: Unchanged main-scheme threat disproves a claimed main-scheme removal

- **WHEN** a Marvel move claims to remove threat from the main scheme and the authoritative before and after states both report `zones.sharedMainScheme[0].tokens.threat` as `12`
- **THEN** the resulting verdict SHALL not credit `threat_resource` or `overall_score` for that move
- **AND** the verdict SHALL identify that the claimed threat-removal effect was not observed

#### Scenario: Side-scheme removal does not claim a main-scheme effect

- **WHEN** a Marvel move claims to remove threat from a side scheme and the authoritative main-scheme threat remains `12`
- **THEN** the evaluator SHALL leave the judge verdict unchanged rather than treating the side-scheme effect as an unobserved main-scheme removal

#### Scenario: An unavailable threat value is not treated as an unchanged value

- **WHEN** either before or after normalized state has no public integer main-scheme threat token
- **THEN** the evaluator SHALL leave the judge verdict unchanged rather than guessing whether threat was removed

### Requirement: Terminal Marvel transitions have priority over positive move reasoning

An authoritative normalized `mode=loss` or `mode=win` in the state resulting from a Marvel move SHALL take priority over contradictory judge prose. A move whose resulting state is a terminal loss SHALL not receive a positive score because of stale or fabricated reasoning. Existing verdict fields and score types SHALL remain compatible with previously stored verdicts.

#### Scenario: The move causing 12/14-to-14/14 loss cannot be positive

- **WHEN** a move's authoritative prior state has main-scheme threat `12` with target `14`, and its resulting state has threat `14` with `mode=loss`
- **THEN** the move verdict SHALL have zero scores and `overall_score=0`
- **AND** stale positive reasoning or fabricated villain hit points SHALL not change that result

#### Scenario: A terminal win remains explicit evidence

- **WHEN** a move's resulting normalized state has authoritative `mode=win`
- **THEN** the verdict SHALL identify the terminal win transition as evidence
- **AND** the evaluator SHALL not reinterpret the state as an in-progress move

### Requirement: Coordinator rule provenance is available for attribution

A player move in an orchestrated game SHALL carry the exact coordinator-provided prompt and server-set provenance identifying its source, orchestrator session, parent job, and child job. Evaluation SHALL present that data as untrusted coordinator evidence separate from the player's reasoning, so a rule conflicting with authoritative state is attributed to the supplied coordinator instruction rather than silently blamed on the player.

#### Scenario: A bad supplied rule is attributed to the coordinator

- **WHEN** a coordinator prompt instructs a player to perform an effect that the authoritative resulting state does not show
- **THEN** the evaluator input SHALL identify the prompt as coordinator-provided and include its provenance
- **AND** the resulting evidence SHALL identify the coordinator instruction as conflicting rather than attributing the rule to the player alone

#### Scenario: Legacy chat moves remain readable

- **WHEN** an older or chat-mode agent move has no coordinator provenance
- **THEN** the evaluator SHALL continue to assemble and grade the move without inventing a source or rejecting the history event

### Requirement: Resolved Marvel option identity is durable

A resolved Marvel enumerated move SHALL retain the producer-confirmed option identity as `payload.marvel_lcg_option` with exactly `id`, `name`, and `event`, where all fields come from the successful option listing that offered the selected identifier. Generic action names, model-authored arguments, and option names alone SHALL NOT synthesize that identity. Old moves without the additive field SHALL remain readable through the legacy action fallback.

#### Scenario: Resolved option identity survives history round-trip

- **WHEN** a Marvel player submits an option identifier that matched a successful enumerated option listing containing its id, name, and event
- **THEN** the durable agent move event SHALL contain `payload.marvel_lcg_option` with those three producer-confirmed fields
- **AND** evaluation SHALL use that object as the move identity


#### Scenario: Normalized listing event metadata is retained

- **WHEN** the successful Marvel options response supplies `event_name` at the response level for the selected option
- **THEN** the durable option identity SHALL use that value as `event` alongside the selected option's producer-confirmed `id` and `name`

#### Scenario: Missing producer metadata is not reconstructed

- **WHEN** a selected option's successful listing lacks its name or event metadata, or only generic action arguments are available
- **THEN** the durable move event SHALL omit `marvel_lcg_option`
- **AND** evaluation SHALL retain the legacy action identity without inventing the missing fields
