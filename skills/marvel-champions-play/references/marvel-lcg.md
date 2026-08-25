# marvel-lcg harness reference

Load this file only when the session platform is `marvel-lcg`. It is a rules-enforcing
engine: the move surface is a list of legal, engine-validated options, not composed card
mutations. The task is to choose well among those options.

## State and pending decisions

Read `get_game_state` before acting. Use neutral `playRound`, `phase`, and `phaseLabel`.
The platform's integer `stepId` is opaque. `pendingSeats` names the seats whose decision
the engine is currently asking for; act only when your seat is present. The platform's
normalised zones resolve cards by meaning and visibility. Do not infer ownership from an
integer object id or from a string that happens to resemble a DragnCards group name.

`players` resources are shown only when the platform can interpret them. Hidden cards stay
hidden. Read the state again after a choice; the state changing and the prompt leaving
your pending set are the confirmation, not the HTTP response.

## Enumerated option surface

Use the `game-service_` prefix shown by the session's tool list:

1. `list_game_options(session_id, player_n)` reads the current prompt and options for the
   requested seat. Retain its `prompt_id` and `prompt_version`; both are required for
   the matching choice.
2. Choose by `option_id`, never by option name. Names are descriptive and are not unique;
   one prompt can contain several options named `Play`. Use each option's resolved target
   card name and type, payment choices, and event context to distinguish them.
3. Submit exactly one choice with `choose_game_option(session_id, player_n, option_id,
   targets, resources, prompt_id, prompt_version)`. The tool validates that the id is
   still pending, that the prompt identity matches, that targets are legal, and that the
   target count fits the option's inclusive range.

For durable evaluation, a successful choice is recorded additively on the agent move as
`payload.marvel_lcg_option` with exactly `{id, name, event}`. The orchestrator copies
`id`, `name`, and `event` only from the matching successful `list_game_options` result;
the submitted `option_id` and the seat's prose cannot fill in missing metadata. The
canonical field is `marvel_lcg_option`, not `option_identity`.

The target-count range is authoritative. If its maximum is `0`, submit no targets and
ignore any non-empty legal-target list. If its minimum is `0`, an empty target selection
is legal. Never identify an option by name, and never submit a target outside the option's
resolved legal set. Card target ownership is checked from the normalised zones.

## Confirmation and rejection

The platform acknowledges submissions without reporting validity. An input it rejects is
discarded silently and the same decision is asked again. A changed prompt or a seat that
leaves `pendingSeats` is the evidence that the choice advanced. If the identical prompt,
option ids, and decision context recur after submission, treat the choice as rejected:
do not resubmit it. Re-read the options, choose a different legal choice, or report the
stuck prompt.

There is no separate phase or turn-advancement call. Ending a turn is itself an
enumerated option when the engine offers it. The engine enforces turn order, phase
advancement, resource payment, the once-per-turn form change, and the legal target set.
An option offered by the engine is affordable and legal; do not compose a separate cost
payment or board mutation around it.

## Neutral play recipes as choices

- To pay and play an ally, upgrade, support, or event, choose the offered option by id
  and submit the payment form the option provides. Do not discard resource cards by hand.
- For a basic attack, choose the attack option and select a target within its range.
- For a basic thwart, choose the thwart option and select the scheme target within its
  range.
- To defend, recover, change form, resolve a forced choice, or finish a turn, choose the
  corresponding currently offered option. The engine performs the rules and reports the
  resulting board in the next state.

The engine can expose a cancel/decline affordance only when the prompt says it is
available. Use that explicit affordance; never invent a magic option id. If a prompt is
not cancellable, a decline is not a legal move.
