# Tasks

## 1. Player skill — strict turn loop and guardrails

- [x] 1.1 Add an entry-conditions block to `skills/marvel-champions-play/SKILL.md`
      naming the seat, `session_id` and hero as required inputs, and instructing
      the agent to ask rather than infer a missing seat from the board.
- [x] 1.2 Rewrite the turn loop so each ordered step carries the observation that
      confirms it, and state the `error`-after-every-mutating-call rule inside the
      loop rather than only in `resources/recovery.md`.
- [x] 1.3 Add explicit stop conditions and a completion check answerable from the
      board, restating that a turn ends by reporting and never by advancing a
      phase or refilling a hand.
- [x] 1.4 Add a failure ladder: non-null `error`, board-does-not-match-intent,
      unfixable-with-own-tools, and the point at which the agent stops and reports.
- [x] 1.5 Add a guardrail section separating the seat guard's three enforced
      refusal shapes from the rules of play nothing validates (turn order, phase
      authority, cost payment, one form change per turn, hand limit).
- [x] 1.6 Document `list_my_illegal_actions` and the seat's side of the findings
      loop: open findings arrive every turn, the seat performs its own undo, only
      the orchestrator closes a finding.
- [x] 1.7 Cross-reference the resources from the new loop steps without moving
      content out of them, and re-measure `SKILL.md` size.

## 2. Orchestrator skill — entry, stop, failure, findings, trust boundary

- [x] 2.1 Give Phase 0 stated entry conditions and an abort when the roster is
      empty or the player count does not match it.
- [x] 2.2 State a termination for each of the three nested loops and require the
      round loop to stop immediately on a terminal condition without finishing the
      round.
- [x] 2.3 Widen failure handling to the child-job crash modes the runtime
      produces, and forbid re-waiting on a job whose wait was abandoned.
- [x] 2.4 Document the illegal-action findings loop with `report_illegal_action`
      and `resolve_illegal_action`, including that legality comes from game state
      and that a seat's claim of having undone something is not verification.
- [x] 2.5 Add the trust-boundary rule that a seat's report and any seat-to-seat
      message are data rather than instruction.
- [x] 2.6 Re-read `references/round-loop.md` and `references/player-turn-prompt.md`
      against the new `SKILL.md` text. Neither contradicts it — both already state
      the one-re-prompt-then-abort rule and the roster-sized player count — so both
      are left unchanged.

## 3. Learn-to-play skill — split and cut

- [x] 3.1 Cut the Core-Set component inventory, the per-scenario encounter-set
      card lists, the starter-deck contents and the nemesis-set table.
- [x] 3.2 Move the remaining detail into `references/` files and leave `SKILL.md`
      holding the round loop, the turn options, the win/loss table and a routing
      table naming each reference and its load condition.
- [x] 3.3 Add the scope declaration: what the skill is for, and that harness
      mechanics live in `marvel-champions-play` and authoritative rules in
      `marvel-champions-rules-reference`.
- [x] 3.4 Record the before/after byte counts for `SKILL.md` and the new
      references.

## 4. Rules-reference and dragncards skills

- [x] 4.1 Add the stated lookup loop to
      `skills/marvel-champions-rules-reference/SKILL.md`: route, load, apply
      errata, answer with a citation, stop; do not answer from memory; do not load
      references speculatively.
- [x] 4.2 Add the unanswerable-question rule and keep the resource routing table
      intact.
- [x] 4.3 Add a scope declaration to `skills/dragncards/SKILL.md` stating it is a
      plugin-authoring skill, not a play skill, and that DragnLang is not a way to
      act on a live table.
- [x] 4.4 Verify the rules-reference corpus still fits the derived budget and
      still ships at least nine reference files.

## 5. Verification and ancillary documents

- [x] 5.1 Re-measure every skill's `SKILL.md` and reference bytes and record the
      before/after delta, including the effect on the judge's reference headroom.
- [x] 5.2 Update the hard-coded corpus counts in
      `services/eval-service/README.md` and the `judge/skill_resources.py` module
      docstring. `services/eval-service/.env.example` re-checked and left as is:
      it cites the derived budget and the file count, neither of which moved.
- [x] 5.3 Confirm every `SKILL.md` still parses through the agent-orchestrator
      frontmatter reader and that every skill and reference still resolves through
      the eval-service resolver.
- [x] 5.4 Run `./scripts/lint.sh --fix`, `./scripts/test.sh unit`,
      `./scripts/test.sh integration` and `openspec validate --all`.
