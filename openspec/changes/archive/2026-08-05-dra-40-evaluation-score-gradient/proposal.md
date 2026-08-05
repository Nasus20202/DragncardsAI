## Why

Every evaluation score the dashboard shows is green. The chip that carries a
verdict's overall score is hard-coded to Hero UI's `success` colour in all three
places it is rendered:

| site | file |
| --- | --- |
| the per-verdict chip inside a move's evaluation list | `features/history/components/history-transcript.tsx` (~line 484) |
| the "latest score" indicator on a graded move's header row | `features/history/components/history-transcript.tsx` (~line 742) |
| each cell of the per-player scorecard | `features/history/components/history-scorecard.tsx` (~line 26) |

So a 2/10 and a 10/10 are the same green, and the colour carries no information
at all — it says only "this was evaluated", which the chip's presence already
says. Scanning a game for the moves the judge marked down means reading every
number.

The score has a fixed, known scale to map onto. The eval-service clamps every
score it parses into 0–10 (`_clamp_score` in `judge/parse.py`) and its verdict
schema declares `overall_score: int = Field(ge=0, le=10)`, so an individual
verdict carries an integer 0–10. The scorecard, however, shows the **mean** of a
player's verdicts at each level (`withAverage` in
`features/history/lib/history-rounds.ts`), so the value that actually has to be
coloured is a real number in 0–10, not an integer.

## What Changes

- The score chip's background becomes a continuous colour ramp over the 0–10
  scale: red at 0, amber at 5, green at 10, interpolated smoothly for every value
  in between. Two averages a tenth of a point apart differ by a tenth of a point
  of colour rather than snapping to the same bucket — which is why this is a ramp
  and not three or five discrete Hero UI colours.
- The ramp is interpolated in **OKLCH**, and its three stops are Hero UI's own
  `--danger`, `--warning` and `--success` token values. Interpolating red and
  green in sRGB passes through a muddy brown at the midpoint; in OKLCH, with an
  amber stop pinned at the middle, 5/10 reads as the same amber Hero UI already
  uses for `warning`.
- The chip's text colour is derived from the computed background's OKLCH
  lightness rather than left fixed, so the number stays legible at every point on
  the ramp. Both text colours are Hero UI tokens (`--snow`, `--eclipse`), which
  are defined on `:root` and therefore identical in the light and dark themes;
  the chip is a solid pill, so its contrast is internal and does not depend on
  the page behind it.
- A score that is missing, `null`, or not a finite number gets **no** ramp colour
  and falls back to the neutral chip. It never renders green. A finite score
  outside 0–10 is clamped to the ends of the ramp, matching what the eval-service
  itself does to a judge's out-of-range answer.
- The three call sites become one `ScoreChip` component so the treatment cannot
  drift apart again. The chip keeps its existing size, variant, shape, spacing
  and position — only the colour derivation changes.

## Capabilities

### Modified Capabilities

- `game-history-ui`: an evaluation score's chip colour is a function of the
  score on a continuous 0–10 red-to-green ramp, rather than a fixed colour.

## Non-goals

- Changing the evaluation section's own identity colour. The verdict rows'
  success-tinted borders and backgrounds, the "N evaluations" toggle, and the
  verdict-detail panel keep the green they have; they mark "this is an
  evaluation", not "this score was good".
- Colouring the per-criterion sub-score chips (`rules legality: 8`, …) in the
  expanded verdict detail. They are neutral `soft`/`default` chips today, are not
  part of the "always green" complaint, and tinting four chips per verdict would
  turn a detail panel into a colour chart.
- Changing what a score means, how it is computed, how verdicts are averaged, or
  the evaluator-version exclusion rule the scorecard already applies.
- Adding a legend, a tooltip, or any new element to explain the ramp. The number
  is displayed next to the colour and remains the authoritative reading.
- Any change to the eval-service, history-service, or the verdict payload.

## Impact

- `services/dashboard/features/history/lib/score-colors.ts` — new module: the
  pure score → OKLCH background/foreground ramp.
- `services/dashboard/features/history/components/score-chip.tsx` — new
  component: the single score chip the three sites now render.
- `services/dashboard/features/history/components/history-transcript.tsx` —
  both score chips render through `ScoreChip`.
- `services/dashboard/features/history/components/history-scorecard.tsx` — the
  scorecard cell renders through `ScoreChip`.
- `services/dashboard/features/history/__tests__/score-colors.test.ts` — new
  unit tests for the ramp.
- `services/dashboard/features/history/__tests__/history-scorecard.test.tsx`,
  `services/dashboard/features/history/__tests__/history-transcript.test.tsx` —
  assertions that a low score and a high score render different colours.
