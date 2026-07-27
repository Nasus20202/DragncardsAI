# Player Prompt Contract

**Referenced by:** SKILL.md

A player agent is a subagent. It has **no memory of previous turns and no conversation history**.
Every prompt must be fully self-contained: everything the seat needs to decide its turn has to be
in the prompt text. If a fact is not in the prompt, the seat does not know it.

**Use the same template for every seat, every round.** Two differently configured agents must
receive identical information in identical structure — a fair comparison requires identical inputs.
Never give one seat richer board detail, extra hints, or tactical suggestions.

---

## Turn prompt template

Fill every placeholder. Do not omit a section; write `none` where a section is empty.

```
You are playing Marvel Champions on DragnCards as a single hero. Load the skill
`marvel-champions-learn-to-play` before acting if you need the rules.

GAME
  session_id: <uuid>
  Your seat: <player1|player2|player3|player4>
  Your hero: <Hero Name> (<alter-ego name>)
  Your current form: <hero|alter-ego>
  Round: <N>
  You are <the first player | not the first player>. Player order this round: <player1, player2, ...>

BOARD
  Villain: <Name> stage <I|II|III>, <current>/<max> HP, <ready|exhausted>, status: <stunned/confused/tough/none>
  Main scheme: <Name>, <current> / <target> threat, acceleration <value>
  Side schemes in play: <Name (threat/target, icons)> | none
  Attachments on villain: <names> | none
  Minions engaged with YOU: <Name (HP, ATK, SCH)> | none
  Minions engaged with other seats: <seat: Name> | none
  Other heroes: <seat: Hero (form, HP, allies in play)> | none

YOUR HERO
  Hit points: <current>/<max>
  Hand: <N> cards — <card names>
  Allies in play: <Name (HP remaining, ready/exhausted)> | none
  Upgrades / supports in play: <Name (ready/exhausted)> | none
  Status cards on you: <stunned|confused|tough|none>
  Your identity card is <ready|exhausted>
  Hand size: <N>

WHAT YOU MAY DO
  This is your player turn. In any order, as many times as you can pay for:
    - Change form (once per turn only)
    - Play allies, upgrades, supports, events, and player side schemes from hand
    - Use a basic power: attack or thwart (hero form) or recover (alter-ego form)
    - Use an ally to attack or thwart (exhaust it; it takes consequential damage)
    - Trigger Action abilities on cards you control
  Execute your decisions with the game-service tools against session_id <uuid>, acting only on
  cards you control.

WHAT YOU MUST NOT DO
  - Do not advance any phase or step. Never call next_step, prev_step, player_end_phase,
    villain_encounter_phase, or villain_end_phase.
  - Do not touch another seat's hero, allies, upgrades, hand, or deck.
  - Do not resolve any part of the villain phase, deal encounter cards, or draw boost cards.
  - Do not spawn subagents.
  - Do not end the round. End your turn by reporting back.

RETURN FORMAT
  Reply with exactly this structure and nothing else:

  ACTIONS:
  1. <what you did> (tool: <tool_name>)
  2. <what you did> (tool: <tool_name>)
  REASONING: <one or two sentences>
  RESULT: form=<hero|alter-ego>, HP=<current>/<max>, hand=<N> cards, allies=<names or none>,
          identity=<ready|exhausted>
  TURN COMPLETE
```

---

## Required return format

The seat's final answer text is the only thing that reaches the orchestrator's context. It must be
short and structured.

| Element        | Requirement                                                                                     |
| -------------- | ------------------------------------------------------------------------------------------------- |
| `ACTIONS:`     | Numbered, **in the order performed**, each naming the game-service tool used                    |
| `REASONING:`   | One or two sentences. Not a transcript of deliberation                                          |
| `RESULT:`      | The resulting state of **its own hero only** — form, hit points, hand size, allies, ready state |
| `TURN COMPLETE`| Literal marker on its own line. Its absence means the turn did not finish cleanly               |

A report without `TURN COMPLETE`, or one that lists actions on another seat's cards or on phase
control, is **not a valid turn report**. Apply the failure handling procedure in SKILL.md: re-prompt
once with a clarification, then abort rather than playing the seat yourself.

A seat that legitimately does nothing still reports: `ACTIONS: none`, a reason, `RESULT:`, and
`TURN COMPLETE`.

---

## Mid-villain-phase decision prompt

Use this shorter template whenever the villain phase produces a decision that belongs to a specific
player: whether to defend, an encounter card choice belonging to the revealing player, a target
choice among that seat's own cards, an obligation resolution, or a first-player tie-break.

```
Marvel Champions — villain phase decision. You are <player1|...>, playing <Hero Name>.
session_id: <uuid>. Round <N>.

SITUATION
  <One paragraph: exactly what is happening and why a decision is needed.>
  <Example: "The villain is attacking you. Base ATK 3, boost card not yet flipped.
   You are in hero form with DEF 2, ready, at 8/10 HP. You control Hawkeye (ready, 3 HP)
   and Maria Hill (exhausted).">

DECISION REQUIRED
  <The exact question, with the concrete options enumerated.>
  <Example: "Choose one: (a) defend with your hero (exhaust, reduce damage by 2),
   (b) defend with Hawkeye (exhaust, Hawkeye takes all the damage),
   (c) do not defend (take full damage to your hero).">

CONSTRAINTS
  - Answer for your hero and your cards only.
  - Do not advance any phase and do not resolve the villain phase.
  - You may execute the mechanical part of your own choice (for example exhausting your own
    defender) but nothing else. The orchestrator resolves the rest.

RETURN FORMAT
  DECISION: <the option you chose>
  REASONING: <one sentence>
  ACTIONS: <tool calls you made, or none>
  DECISION COMPLETE
```

Send this prompt with `prompt_player_agent` and block on `wait_for_subagent` exactly as with a turn
prompt. Resolve nothing until the seat has answered. If the seat fails to answer validly twice,
abort per SKILL.md — do not pick the option yourself.

---

## Fairness rules for prompt construction

- **Identical structure for every seat.** Same section headings, same order, same level of detail.
- **Identical scope of information.** Every seat sees the same public board; each seat sees only its
  own hand. Never leak one seat's hand to another.
- **No coaching.** Never suggest a line of play, rank the options, flag a "best" target, or warn a
  seat about a threat it could read off the board itself. The seat's decision quality is the thing
  being measured.
- **No carry-over.** Do not include a seat's previous turn report in the next turn's prompt. The
  board summary already reflects its consequences, and including it would give a seat with a longer
  history an advantage over one without.
- **Facts only.** Everything in the BOARD and YOUR HERO sections must come from the actual game
  state (read via a subagent) or from an action you or a seat verifiably took this round. Never
  estimate a hit point total or a threat count.
