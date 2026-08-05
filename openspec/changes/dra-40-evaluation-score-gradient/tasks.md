## 1. Establish the score domain and every render site

- [x] 1.1 Read the eval-service's own bounds for an overall score (`_clamp_score` in `src/eval_service/judge/parse.py`, `overall_score` on `src/eval_service/schemas/verdict.py`) and record that a verdict carries an integer clamped to 0–10
- [x] 1.2 Confirm from `withAverage`/`buildPlayerScorecard` in `features/history/lib/history-rounds.ts` that the scorecard colours a mean, so the ramp has to be continuous over reals in 0–10
- [x] 1.3 Enumerate every site that renders an overall score with a colour and confirm the list is complete: the per-verdict chip and the latest-score indicator in `history-transcript.tsx`, and the scorecard cell in `history-scorecard.tsx`
- [x] 1.4 Record which score-adjacent colours are deliberately left alone: the evaluation rows' success-tinted borders/backgrounds, the "N evaluations" toggle, and the neutral per-criterion sub-score chips

## 2. The colour ramp

- [x] 2.1 Add `features/history/lib/score-colors.ts` with `SCORE_MIN`/`SCORE_MAX` and a pure `scoreColors(value)` returning the chip's background and foreground, or `null` for a value that cannot be placed on the ramp
- [x] 2.2 Define the ramp's three stops in OKLCH from Hero UI's `--danger`, `--warning` and `--success` token values, so 0 is Hero UI's red, 5 its amber, and 10 its green
- [x] 2.3 Interpolate lightness, chroma and hue between the bracketing stops in OKLCH so the midpoint is amber rather than the brown an sRGB red-to-green blend produces
- [x] 2.4 Return `null` for a non-number, `null`/`undefined`, `NaN`, and a non-finite number, so bad input falls back to the neutral chip instead of any ramp colour
- [x] 2.5 Clamp a finite out-of-range score to `SCORE_MIN`/`SCORE_MAX` rather than extrapolating the ramp past its ends
- [x] 2.6 Derive the foreground from the computed background's OKLCH lightness against the crossover where light and dark text give equal contrast, using the `--snow` and `--eclipse` Hero UI tokens, which are defined on `:root` and so are the same in both themes

## 3. One chip for every score

- [x] 3.1 Add `features/history/components/score-chip.tsx` rendering the existing `Chip` (`size="sm" variant="primary"`) with the ramp colours applied, and returning `null` when `formatScore` has no number to show
- [x] 3.2 Render the scorecard cell in `history-scorecard.tsx` through `ScoreChip`, keeping the em-dash empty state and the "avg of N" caption unchanged
- [x] 3.3 Render the per-verdict chip in `history-transcript.tsx` through `ScoreChip`, keeping its `history-eval-score-<seq>` test id
- [x] 3.4 Render the latest-score indicator in `history-transcript.tsx` through `ScoreChip`, keeping the surrounding reveal button untouched
- [x] 3.5 Confirm nothing else about these chips changed — same size, variant, shape, position, spacing, and surrounding markup

## 4. Tests

- [x] 4.1 Unit test the ramp's ends: 0 is Hero UI's danger red and 10 its success green
- [x] 4.2 Unit test the midpoint: 5 is Hero UI's warning amber, and its hue lies between the two ends
- [x] 4.3 Unit test that hue increases monotonically across the scale, so no value on the ramp is redder than a lower one
- [x] 4.4 Unit test fractional values: 7.4 and 7.6 produce different backgrounds
- [x] 4.5 Unit test the boundaries: `null`, `undefined`, `NaN`, `Infinity` and a non-number all yield no ramp colour
- [x] 4.6 Unit test clamping: -5 matches 0 and 42 matches 10
- [x] 4.7 Unit test the foreground rule: every in-range score's foreground is a Hero UI text token, and a background below the contrast crossover selects the light one
- [x] 4.8 Component test: the scorecard renders a low average and a high average in different colours
- [x] 4.9 Component test: the transcript renders a low-scoring and a high-scoring verdict in different colours, and the same score in the same colour in both of the transcript's sites

## 5. Verification

- [x] 5.1 Run `./scripts/lint.sh --fix`
- [x] 5.2 Run `./scripts/test.sh unit` and confirm no suite regressed against its baseline
- [x] 5.3 Run `~/.local/share/pnpm/openspec validate --all` and confirm the only failure is the pre-existing `spec/typed-game-actions` one
- [x] 5.4 View a scored game in the running dashboard and confirm the chips differ by score across the transcript and the scorecard, in both the light and the dark theme
