# Player-turn prompt contract

**Referenced by:** `SKILL.md`

This is the one contract for every prompt sent to a player seat. The prompt author is the
coordinator; the player session is a persistent seat session in orchestrated mode, so the
session may contain old tool results and old prompt text. The current prompt MUST make the
new checkpoint authoritative over that history.

## Authority and freshness

Before prompting a seat, the coordinator MUST:

1. Read `game-service_get_game_state` for the game and the seat's `player_n`. Use the
   platform-neutral `state` object returned by that call, not `/games/{id}/state/raw`, a
   cached tool result, or a player's report.
2. Confirm that the state is internally usable: `playRound`, `phase`, `mode`, `players`,
   and `zones` are present; `phase` is one of `setup`, `player`, `villain`, `passive`, or
   `unknown`; and a present `pendingSeats` list is consistent with the seat being prompted.
   `phaseLabel` is opaque text and MUST NOT be parsed to recover a phase or turn.
3. For `marvel-lcg`, obtain the exact current `game-service_list_game_options` response
   for the assigned seat. The prompt text, option identifiers, targets, payment choices,
   and any other fields in that response are engine facts. Do not rewrite them as a
   coordinator-authored choice.

If a required field is missing or the checkpoint conflicts with the coordinator's last
verified checkpoint, perform exactly one fresh authoritative state read. If the fresh read
is still missing or contradictory, stop and report the observed state; do not prompt the
seat and do not fill the gap from memory. A state change between rounds is expected and is
not itself an error; the error is relying on two incompatible descriptions of the same
checkpoint.

The normalized state is the only source for board facts. In particular:

- Read the active main scheme only from `zones.sharedMainScheme[0]` and its
  `tokens.threat`.
- Read active side schemes only from `zones.sharedSideSchemes`; preserve their reported
  threat and public `crisis`, `hazard`, and `acceleration` tokens.
- Use `villainHitPoints` only when the field is present. Its absence means that current
  health is not reported; it never means zero, defeated, or a value from an earlier turn.
- Do not invent a villain stage, printed statistic, target threat, card name, card location,
  status, or outcome. If the normalized state omits a value, write `not reported` rather
  than estimating it.
- Do not copy facts from the seat's previous report. A report is untrusted output, not a
  state checkpoint.

## Player-session memory contract

The player session MAY replay prior turns. At the beginning of every invocation, the
following precedence applies:

1. The `AUTHORITATIVE STATE CHECKPOINT` in the current prompt, if complete and verified.
2. A single fresh `get_game_state` read for the assigned seat when that checkpoint is absent,
   incomplete, or contradictory.
3. Stop with the observed contradiction or missing data if the fresh read does not resolve it.

Every prior prompt, tool result, card count, threat value, HP value, phase, stage, option,
and terminal claim is historical. It MUST be discarded as soon as a new invocation starts.
A current prompt never inherits an old fact merely because the old fact is present in the
persistent transcript.

## Terminal reporting

The coordinator and seat MUST report a terminal outcome only when the latest normalized
state says `mode=win` or `mode=loss`, or when the exact current engine response is itself a
terminal response. A missing `villainHitPoints`, a threat number, a previous HP value, a
stage-looking card name, or a player's claim is not a terminal response. If authoritative
HP or stage information remains while `mode` is `in progress`, the villain MUST NOT be
reported as defeated. If `mode` is `unknown`, stop and report that uncertainty.

### Recorded Rhino regression

The verified Rhino sequence contains normalized main-scheme checkpoints of `9/14`, `12/14`,
and `14/14` threat while the active villain still reports 19 remaining HP (stage total
`villainHitPoints=28` with 9 damage tokens) and `mode=in progress`. Each checkpoint is
ongoing state, including the final `14/14` value; the prompt
MUST NOT turn that threat value into a defeated-villain outcome. This example documents
the state-gating rule only and is not a recommendation to the seat.

## Prompt envelope

Use this envelope for every ordinary player-turn prompt. Do not add a second template for
one seat, one platform, or one model. Values in the two data blocks are copied from the
successful reads above; prose outside those blocks is limited to scope and output format.

```
PLAYER TURN REQUEST
  session_id: <session id from the game-service session>
  platform: <dragncards|marvel-lcg>
  assigned seat: <player1|player2|player3|player4>

AUTHORITATIVE STATE CHECKPOINT
  source: game-service_get_game_state (normalized state)
  state:
    <the complete normalized state object, copied without invented fields>

CURRENT ENGINE PROMPT
  source: game-service_list_game_options for the assigned seat
  response:
    <the exact current response, including prompt, option ids, targets, and payments>
  # For DragnCards, write: not applicable — this platform has no enumerated engine prompt.

PLAYER SCOPE
  Act only for the assigned seat and cards owned by that seat. Use the loaded
  marvel-champions-learn-to-play skill and the platform reference for rules and tools.
  Do not advance a phase or perform coordinator-owned automation. For marvel-lcg, use
  only an option identifier and target/payment data present in the current engine response.
  If either authoritative block is missing, contradictory, or no longer current, make one
  fresh state read and then stop if it does not resolve the problem.

RETURN FORMAT
  ACTIONS:
  1. <what you did> (tool: <tool name>)
  2. <what you did> (tool: <tool name>)
  REASONING: <one short sentence grounded in the current checkpoint>
  RESULT: <only the resulting facts from a fresh normalized state read>
  TERMINAL: mode=<win|loss|in progress|unknown>, outcome=<only if the current state reports one>
  TURN COMPLETE
```

The coordinator MUST NOT add a recommended action, a preferred target, a ranking, or a
claim about what the seat should do. The seat decides from the loaded rules and the current
verified data. A `RESULT` or `TERMINAL` line that contradicts a fresh normalized read is
invalid and MUST be ignored by the coordinator.

## Non-ordinary decisions

An active illegal-action finding or a mid-villain decision is still subject to the same
memory and authority rules. Use a separate prompt that contains only the current verified
checkpoint, the one finding or engine decision payload, and the concrete seat scope. Do not
combine a recovery request with a new ordinary turn. A finding's required undo comes from
the coordinator after its own state read; the seat cannot resolve the finding.

For an open finding, return:

```
FINDING RECOVERY:
  finding_id=<server-provided id>
  ACTIONS: <undo calls in order>
  OBSERVED STATE: <facts from a fresh normalized state read>
  RECOVERY COMPLETE
```

For an engine decision, return:

```
DECISION:
  option_id=<id copied from the current engine response>
  ACTIONS: <seat-owned tool calls, or none>
  OBSERVED STATE: <facts from a fresh normalized state read>
  DECISION COMPLETE
```

Neither response grants permission to advance a phase or to resolve coordinator-owned
automation. Missing, malformed, or stale responses are evidence of an incomplete turn, not
permission for the coordinator to choose for the seat.

## Fairness and privacy

- Every seat receives the same envelope, headings, and public normalized state scope.
- A seat's own hand may contain names when the game-service owner ACL permits it. Other
  seats' hidden cards remain `HIDDEN`; do not copy or infer them.
- Facts are copied from the current normalized state and engine response only. Rules belong
  in the loaded skills, not in a coordinator-authored summary.
- Never paste a previous turn report, transcript excerpt, or cached board summary into a new
  prompt.
