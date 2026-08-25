# enumerated-game-options Specification

## Purpose
The enumerated-game-options capability exposes each platform's legal move set through one
platform-neutral option list and validates submissions against the currently pending decision.

## Requirements

### Requirement: An enumerating platform exposes its legal move set as options

The system SHALL expose, for a session whose platform's engine adjudicates the rules and enumerates
the legal move set, that move set to the agent as an option list for a named seat, and SHALL expose
the submission of exactly one of those options as the way that seat moves. The contract SHALL be
platform-neutral: the option list, the option fields and the submission form SHALL be identical
whichever enumerating platform produced them, and SHALL carry no platform-specific transport detail —
no nested JSON strings, no un-normalised prompt text, and no bare identifier the agent cannot resolve.

The option list SHALL be produced only for a seat the platform is currently asking to decide. A seat
with no pending decision SHALL yield an empty option list, and that SHALL be reported as an empty
result rather than as an error, so a caller can distinguish "nothing to do" from "something failed".

The option surface SHALL NOT be synthesised for a platform whose engine does not enumerate legal
moves; such a request SHALL be refused with an error naming the session's platform and the move
surface it does offer.

#### Scenario: A seat with a pending decision gets its option list
- **WHEN** a client lists the options for a seat the platform is asking to decide
- **THEN** the response SHALL carry the prompt, the asked seat, and one entry per legal option
- **AND** no entry SHALL carry a nested JSON string or an unresolved bare identifier

#### Scenario: A seat with nothing pending gets an empty list
- **WHEN** a client lists the options for a seat with no pending decision
- **THEN** the response SHALL be an empty option list with a success status
- **AND** SHALL NOT be an error

#### Scenario: A non-enumerating platform refuses the option surface
- **WHEN** a client lists or submits options for a session whose platform does not enumerate legal moves
- **THEN** the request SHALL be refused with an error naming that session's platform and its own move surface
- **AND** no option list SHALL be fabricated

### Requirement: An option is identified by its option id, never by its name

Every option SHALL carry a stable option id supplied by the platform's engine, and that id SHALL be
the option's only identity for listing, display, selection and submission. An option's name SHALL be
treated as descriptive text only.

Option names SHALL NOT be assumed unique within one prompt: a single prompt is known to return several
distinct options sharing one name. The system SHALL therefore never key an option map by name, never
deduplicate options by name, and never accept a submission that identifies an option by name.

#### Scenario: Two options sharing a name stay distinguishable
- **WHEN** a prompt returns three options of which two share the name `Play`
- **THEN** all three SHALL appear in the option list with distinct option ids
- **AND** neither of the two sharing a name SHALL be dropped, merged, or renamed

#### Scenario: A submission identifies an option by id
- **WHEN** a client submits a choice
- **THEN** the submission SHALL identify the option by its option id
- **AND** a submission that identifies an option by name SHALL be refused as a bad request

### Requirement: Each option is enriched with its targets resolved from the state

Each option SHALL be enriched, before it reaches the agent, with the resolved identity of every card
it names — at minimum each target card's name and card type, resolved from the same game state the
agent is reading. The enrichment SHALL cover the option's legal targets and the cards named by its
payment options.

This is required for the option list to be usable at all: the engine names targets as bare object
identifiers, and two options sharing a name are distinguishable to an agent only by what they act on.
An option whose targets cannot be resolved SHALL still be listed, with the unresolved target reported
as unresolved rather than omitted, so an option is never silently dropped from the legal move set.

The enrichment SHALL respect the seat's visibility: a card the seat is not permitted to see SHALL be
reported in the hidden form rather than by name.

#### Scenario: Two same-named options are told apart by their targets
- **WHEN** a prompt returns two options both named `Play` acting on different cards
- **THEN** each listed option SHALL carry its target card's name and card type
- **AND** an agent SHALL be able to choose between them from the option list alone

#### Scenario: An unresolvable target is reported, not dropped
- **WHEN** an option names a target card that cannot be resolved in the current state
- **THEN** the option SHALL still appear in the list
- **AND** that target SHALL be reported as unresolved rather than omitted

#### Scenario: A target the seat cannot see is not named
- **WHEN** an option names a target the asked seat is not permitted to see
- **THEN** the enrichment SHALL report that target in the hidden form
- **AND** SHALL NOT disclose its name

### Requirement: The target-count range is authoritative over the legal-target list

Every option SHALL carry a target-count range as an inclusive minimum and maximum, and that range
SHALL be authoritative. When the maximum is zero the option SHALL be presented as taking no targets
even when a non-empty legal-target list is present, and that legal-target list SHALL be ignored rather
than shown, because presenting it invites a submission the engine will not accept.

A submission whose target count falls outside the option's range, or that names a target the option
does not list as legal, SHALL be refused by us before anything is sent to the platform, with an error
naming the option, the range, and the offending targets. A count within the range SHALL be accepted,
including a count of zero where the minimum is zero.

#### Scenario: A zero-maximum option takes no targets
- **WHEN** an option reports a target-count range of `0` to `0` together with a non-empty legal-target list
- **THEN** the listed option SHALL report that it takes no targets
- **AND** the legal-target list SHALL NOT be presented to the agent

#### Scenario: A choice of none is legal where the minimum is zero
- **WHEN** an option reports a target-count range of `0` to `6` and a client submits an empty target list
- **THEN** the submission SHALL be accepted and forwarded to the platform

#### Scenario: A target count above the maximum is refused locally
- **WHEN** a client submits three targets for an option whose target-count range is `1` to `1`
- **THEN** the submission SHALL be refused with an error naming the option and its range
- **AND** nothing SHALL be sent to the platform

#### Scenario: A target the option does not permit is refused locally
- **WHEN** a client submits a target that is not in the option's legal-target list
- **THEN** the submission SHALL be refused with an error naming the offending target
- **AND** nothing SHALL be sent to the platform

### Requirement: Prompt text is normalised before it reaches the agent

The prompt accompanying an option list SHALL be normalised before it is exposed: leading and trailing
whitespace and newlines SHALL be removed, interior runs of whitespace SHALL be collapsed, and purely
decorative runs of punctuation SHALL be removed. The prompt's own words SHALL be preserved exactly —
normalisation SHALL remove only presentation, never content.

This is required because platform prompt text is known to arrive with leading newlines and decorative
dash runs intended for a graphical client. A prompt that normalises to nothing SHALL be reported as an
empty prompt, and the option list SHALL still be served, because the options are the decision and the
prompt is a label.

The asked seat or seats SHALL be reported alongside the prompt, so a caller never has to infer whose
decision it is.

#### Scenario: A decorated prompt is normalised
- **WHEN** the platform's prompt is `"\n--- Spider-Man's Turn (1) ---"`
- **THEN** the exposed prompt SHALL read `Spider-Man's Turn (1)`
- **AND** the wording inside SHALL be unchanged

#### Scenario: A prompt that is only decoration becomes empty
- **WHEN** the platform's prompt consists only of whitespace and decorative punctuation
- **THEN** the exposed prompt SHALL be empty and the option list SHALL still be served

#### Scenario: The asked seat is reported with the prompt
- **WHEN** an option list is served
- **THEN** the response SHALL name the seat or seats the platform is asking
- **AND** a caller SHALL NOT have to infer them from the options

### Requirement: A cancel affordance is exposed only when the platform offers one

The option list SHALL expose a cancel-or-decline affordance for a prompt when, and only when, the
platform reports that the prompt can be cancelled. When the platform does not offer it, the affordance
SHALL be absent from the response and a submission that attempts it SHALL be refused before anything
is sent, with an error stating that the prompt cannot be declined.

Declining SHALL be expressed in the neutral contract as its own explicit form rather than as a
magic option id, and each platform's driver SHALL translate it into that platform's decline
representation.

#### Scenario: A cancellable prompt exposes the affordance
- **WHEN** the platform reports a prompt as cancellable
- **THEN** the option list SHALL report that declining is available
- **AND** a decline submission SHALL be forwarded to the platform in that platform's decline form

#### Scenario: A non-cancellable prompt does not expose the affordance
- **WHEN** the platform reports a prompt as not cancellable
- **THEN** the option list SHALL report that declining is unavailable

#### Scenario: Declining a non-cancellable prompt is refused locally
- **WHEN** a client submits a decline for a prompt the platform reports as not cancellable
- **THEN** the submission SHALL be refused with an error stating the prompt cannot be declined
- **AND** nothing SHALL be sent to the platform

### Requirement: A choice outside the current option set is refused, not forwarded

A submission SHALL be validated against the option set currently pending for the addressed seat, and
SHALL be refused by us — with an error naming the submitted option id and listing the option ids that
are pending — when the submitted option id is not among them. Nothing SHALL be sent to the platform
for a refused submission.

This SHALL apply equally when no decision is pending for the seat, when the seat is not one the
session holds, and when the pending prompt has changed since the option list was read. In the last
case the refusal SHALL state that the prompt has moved on, so a caller re-reads the options rather
than retrying the same choice.

The refusal SHALL be ours rather than the platform's because an enumerating engine is not required to
report an unacceptable submission: a submission can be answered with a success status and silently
discarded, and re-raised prompts can drive an unbounded retry loop.

#### Scenario: An option id that is not pending is refused
- **WHEN** a client submits an option id that is not in the seat's currently pending option set
- **THEN** the submission SHALL be refused with an error naming the submitted id and the pending ids
- **AND** nothing SHALL be sent to the platform

#### Scenario: A submission for a seat with nothing pending is refused
- **WHEN** a client submits a choice for a seat the platform is not currently asking
- **THEN** the submission SHALL be refused with an error stating that the seat has no pending decision
- **AND** nothing SHALL be sent to the platform

#### Scenario: A stale choice is refused with a re-read instruction
- **WHEN** a client submits a choice from an option list the platform has since replaced with a different prompt
- **THEN** the submission SHALL be refused with an error stating the prompt has moved on
- **AND** the error SHALL direct the caller to re-read the current options

#### Scenario: A valid choice is forwarded once
- **WHEN** a client submits an option id that is in the seat's pending option set with a target count inside its range
- **THEN** the submission SHALL be forwarded to the platform exactly once
- **AND** the result SHALL report whether the platform's prompt was resolved rather than merely that the submission was sent
