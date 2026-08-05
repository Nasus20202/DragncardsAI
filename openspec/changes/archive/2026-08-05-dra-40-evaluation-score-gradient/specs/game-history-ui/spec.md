## ADDED Requirements

### Requirement: Evaluation score colour reflects the score

Wherever the dashboard renders an evaluation's overall score, the colour it renders it in SHALL be a function of that score and SHALL NOT be a fixed colour.

A score at the bottom of the scale SHALL be red and a score at the top SHALL be
green, so that a poorly graded move is distinguishable from a well graded one
without reading the number. A fixed colour makes the chip say only "this was
evaluated", which its presence already says.

The colour SHALL be a **continuous ramp** across the scale rather than a small
number of discrete bands. The per-player scorecard shows the mean of a player's
verdicts, not a single verdict, so the value being coloured is a real number; two
averages a tenth of a point apart SHALL differ by a correspondingly small amount of
colour rather than both landing on one band's colour.

The scale being mapped SHALL be 0 to 10 inclusive — the range the eval-service
clamps every parsed score into and the range its verdict schema declares — with the
ramp's midpoint at 5.

The ramp SHALL be interpolated in a perceptually uniform colour space, and its
midpoint SHALL read as a clear amber. Interpolating red to green in sRGB passes
through a muddy brown at the middle of the scale, which reads as a rendering fault
rather than as a middling score.

The colour of the score's text SHALL be derived from the computed background rather
than fixed, so that the number remains legible at every point on the ramp, in both
the light and the dark theme.

A score that is absent, `null`, or not a finite number SHALL NOT be given a ramp
colour. Such a value SHALL fall back to the dashboard's neutral chip colour, and
SHALL NOT be rendered in the colour of a high score. A finite score outside 0 to 10
SHALL be clamped to the nearer end of the ramp rather than extrapolated or rejected.

Every place an overall score is rendered — the per-verdict chip in a move's
evaluation list, the latest-score indicator on a graded move, and each cell of the
per-player scorecard — SHALL use the same mapping, so the same number is never shown
in two different colours.

#### Scenario: A low score and a high score are different colours
- **WHEN** the transcript renders one verdict scoring 2 out of 10 and another scoring 9 out of 10
- **THEN** the two score chips SHALL be rendered in different colours, the 2 towards the red end of the ramp and the 9 towards the green end

#### Scenario: The middle of the scale is amber
- **WHEN** a score of 5 out of 10 is rendered
- **THEN** its colour SHALL be a clear amber, and SHALL NOT be brown, grey, or either end colour of the ramp

#### Scenario: Two close averages are close colours, not identical ones
- **WHEN** the scorecard renders one player's average of 7.4 and another player's average of 7.6
- **THEN** the two cells SHALL be rendered in different colours

#### Scenario: A score is legible against its own colour
- **WHEN** a score is rendered anywhere on the ramp, in either the light or the dark theme
- **THEN** the text colour SHALL be chosen from the computed background's lightness so the number stays readable against it

#### Scenario: A missing score is not coloured as a good one
- **WHEN** a score is absent, `null`, or not a finite number
- **THEN** the dashboard SHALL NOT apply a ramp colour, and SHALL NOT render the value in the colour used for a top score

#### Scenario: An out-of-range score is clamped to the ramp
- **WHEN** a finite score below 0 or above 10 is rendered
- **THEN** it SHALL be given the colour of the nearer end of the ramp

#### Scenario: The same score is the same colour everywhere it appears
- **WHEN** the same overall score appears as a verdict chip, as a move's latest-score indicator, and in a scorecard cell
- **THEN** all three SHALL be rendered in the same colour
