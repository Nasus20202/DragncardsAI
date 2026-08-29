## Context

DRA-83 makes the game-service normalized Marvel state authoritative: the current main scheme is `zones.sharedMainScheme[0]` with `tokens.threat`, the public side schemes are in `zones.sharedSideSchemes`, and terminal state is represented by the normalized `mode`. Eval-service already correlates an agent move with the nearest prior and resulting game-service state, but it currently sends those facts to a judge without a deterministic consistency check. A judge can therefore repeat an action's claimed effect even when the resulting state shows no change, or reward a move immediately before a terminal loss.

The history store keeps JSON payloads verbatim and tolerates additive fields. The orchestrator already resolves Marvel choices from `list_game_options`; the durable move event must retain that producer-confirmed identity and must distinguish a coordinator's instruction from the player's own reasoning without changing the shared verdict shape.

## Goals / Non-Goals

**Goals:**

- Make authoritative normalized before/after state the final arbiter for the two high-impact Marvel false-positive classes: an unobserved threat-removal effect and a terminal transition.
- Keep the validator deterministic, side-effect free, and limited to public normalized state.
- Preserve the coordinator prompt, its source, and stable job/session provenance on a seat move so an evaluator can attribute a conflicting supplied rule correctly.
- Use the resolved Marvel option object as the durable action identity, including the option event, while retaining existing DragnCards action compatibility.
- Keep existing verdict consumers compatible by changing only scores, rationale, and flags, and by accepting old history rows with absent additive fields.

**Non-Goals:**

- No re-scoring or mutation of verdicts already stored in history.
- No attempt to infer printed card effects, hidden information, or rules from raw engine state.
- No changes to judge response parsing, score field names, platform normalization, or the DRA-81/DRA-84 owned skill and prompt/reference files.

## Decisions

### Validate only the normalized Marvel state

A move validator receives the `MoveInput`'s `prior_state` and `resulting_state` and first requires the DRA-83 normalized shape (`playRound`, `phase`, `phaseLabel`, `players`, and `zones`). It reads the first public card in `sharedMainScheme` and its integer `tokens.threat`; missing, hidden, malformed, or raw state is treated as unavailable rather than guessed. This reuses the same public projection sent to the judge and cannot bypass the existing hidden-card rules.

### Make terminal outcomes an evidence override

When the resulting normalized state has authoritative `mode=loss`, a move verdict is forced to zero for all four criteria and `overall_score`, with a terminal-loss flag and an explanatory rationale. The override is applied after parsing the judge response and before history write-back, so stale villain HP or positive prose cannot survive. A normalized `mode=win` transition is likewise marked as terminal evidence and cannot be replaced by a contradictory non-terminal interpretation; the parsed positive scores remain otherwise useful because winning does not itself prove every move was optimal. Existing verdict fields remain the sole wire schema.

### Check claimed main-scheme removal against main-scheme threat

A conservative claim detector examines only the recorded durable action identity, arguments, and the player's stated reasoning for a threat-removal phrase that explicitly names the main scheme. If both authoritative main-scheme threat values are available and equal, the validator sets `threat_resource` to zero, caps `overall_score` at zero for that move, and adds an unobserved-effect flag. Claims that explicitly target a side scheme do not trigger this main-scheme check. This deliberately avoids claiming that a move removed threat when no producer evidence says so; a missing state or an action without an explicit main-scheme removal claim remains judge-scored.

### Carry coordinator provenance as additive history data

For a child/subagent move, the orchestrator adds a `prompt_provenance` object to the agent payload containing the coordinator source, the exact prompt text, the child job id, parent job id, and orchestrator session id. Top-level chat moves keep the legacy payload shape. Eval assembly validates and carries this object into `MoveInput`; the judge prompt labels it as coordinator-provided, untrusted rule input that must be checked against state and must not be blamed on the player when it conflicts with authoritative evidence. The validator also emits a coordinator-conflict flag when a coordinator prompt itself claims the unobserved effect.

### Preserve producer-confirmed Marvel option identity

The orchestrator persists `payload.marvel_lcg_option` only when the submitted `option_id` matches a successful `list_game_options` result and the producer supplied all of `id`, `name`, and `event`. The extractor accepts the real normalized response's top-level `event_name` as the event source, while retaining support for option-level event fields. Eval's `recorded_action` prefers this identity and falls back to the legacy intended action for old rows. Generic action names and model arguments never synthesize missing identity.

## Data flow

```text
normalized state events + agent move
        │
        ├─ assemble prior/resulting state and prompt provenance
        │
        ├─ judge receives public state, action, reasoning, provenance
        │
        └─ parsed verdict → deterministic Marvel evidence validator
                 │
                 └─ corrected existing VerdictPayload → evaluator history event
```

## Risks / Trade-offs

- A textual claim detector can miss an unusual description, so it is intentionally conservative and never turns an unrecognised action into a penalty.
- Terminal loss zeroes a move's score even when the losing condition was caused by an earlier move; the move's resulting state is still the authoritative evidence available at that target, and the requirement prioritizes preventing the known false positive immediately before loss.
- Provenance adds coordinator prompt text to an already durable event. It is bounded when rendered to the judge and remains data in a user-message section, not a system instruction; no private game state is copied into it.
- Existing rows without provenance or option identity remain readable and continue through legacy fallbacks.
