/**
 * The colour an evaluation score is shown in.
 *
 * A score chip used to be green whatever the score was, so the colour said only
 * "this was evaluated" — which the chip's presence already said. It is now a
 * continuous red → amber → green ramp over the score scale.
 *
 * The ramp is continuous rather than a handful of bands because the per-player
 * scorecard colours an *average* of a player's verdicts, not a single verdict:
 * averages of 7.4 and 7.6 are genuinely different and should not share a colour.
 */

/**
 * The score scale, inclusive at both ends.
 *
 * The eval-service clamps every score it parses from a judge into this range
 * (`_clamp_score` in `services/eval-service/src/eval_service/judge/parse.py`) and
 * its verdict schema declares `overall_score: int = Field(ge=0, le=10)`, so an
 * individual verdict carries an integer 0–10. The scorecard averages verdicts, so
 * the value this module has to place on the ramp is a real number in that range.
 */
export const SCORE_MIN = 0;
export const SCORE_MAX = 10;

/** A colour in OKLCH: perceptual lightness, chroma, and hue in degrees. */
interface OklchColor {
  l: number;
  c: number;
  h: number;
}

/** One stop of the ramp, at a normalised position in `[0, 1]`. */
interface RampStop {
  position: number;
  color: OklchColor;
}

/**
 * The ramp's stops, in OKLCH.
 *
 * The values are Hero UI's own `--danger`, `--warning` and `--success` theme
 * tokens, so a score chip stays inside the app's palette: the bottom of the scale
 * is exactly the red Hero UI uses for a danger chip and the top is exactly the
 * green the score chip used to be pinned to.
 *
 * The amber stop is pinned at the middle for a reason. Blending red into green
 * directly — in sRGB especially, but in any two-stop ramp — passes through a
 * muddy brown around the midpoint, which reads as a rendering fault rather than
 * as a middling score. Interpolating in OKLCH between three stops keeps chroma up
 * and puts a clear amber at 5/10.
 *
 * Hero UI's dark theme shifts `--danger` and `--warning` slightly (it leaves
 * `--success` alone). The stops are not re-read per theme: the chip is a solid
 * pill, so its legibility depends on its own background against its own text, not
 * on the page behind it, and the shift is far smaller than one step of the ramp.
 */
const SCORE_RAMP: readonly RampStop[] = [
  // --danger
  { position: 0, color: { l: 0.6532, c: 0.2328, h: 25.74 } },
  // --warning
  { position: 0.5, color: { l: 0.7819, c: 0.1585, h: 72.33 } },
  // --success
  { position: 1, color: { l: 0.7329, c: 0.1935, h: 150.81 } },
];

/**
 * The lightness at which dark text overtakes light text on the chip.
 *
 * It is the crossover point: for a background lighter than this, near-black text
 * has the better contrast ratio; for a darker one, near-white does. Every stop of
 * the ramp above happens to sit above it, so in practice the whole 0–10 scale
 * takes dark text and the number does not flip colour part-way along the ramp.
 * The rule is applied to the computed background rather than assumed, so the
 * foreground stays correct if a stop is ever darkened.
 */
const DARK_TEXT_MIN_LIGHTNESS = 0.63;

/**
 * Hero UI's near-white and near-black text tokens. Both are defined on `:root`
 * rather than per theme, so they resolve to the same colours in the light and
 * dark themes.
 */
export const LIGHT_TEXT = "var(--snow)";
export const DARK_TEXT = "var(--eclipse)";

/**
 * The text colour a background of the given OKLCH lightness takes.
 *
 * Exported so the rule can be checked on both sides of the crossover: the ramp's
 * current stops all sit above it, so `scoreColors` alone only ever exercises the
 * dark branch.
 */
export function textColorForLightness(lightness: number): string {
  return lightness >= DARK_TEXT_MIN_LIGHTNESS ? DARK_TEXT : LIGHT_TEXT;
}

/** The background and text colour for one score. */
export interface ScoreColors {
  /** A CSS colour for the chip's background. */
  background: string;
  /** A CSS colour for the score text, legible against `background`. */
  foreground: string;
}

function lerp(from: number, to: number, t: number): number {
  return from + (to - from) * t;
}

function trim(value: number, digits: number): number {
  return Number(value.toFixed(digits));
}

/**
 * The colour a score is shown in, or `null` when the value cannot be placed on
 * the ramp.
 *
 * A `null`, `undefined`, `NaN`, infinite, or non-numeric score returns `null` so
 * the caller falls back to the neutral chip. Returning a ramp colour for input
 * like that would put unevaluated or malformed data somewhere on a red-to-green
 * scale, and the end it landed on would be read as a judgement.
 *
 * A finite score outside the scale is clamped to the nearer end, which is what
 * the eval-service does to a judge's out-of-range answer.
 */
export function scoreColors(
  value: number | null | undefined
): ScoreColors | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;

  const clamped = Math.min(SCORE_MAX, Math.max(SCORE_MIN, value));
  const position = (clamped - SCORE_MIN) / (SCORE_MAX - SCORE_MIN);

  let lower = SCORE_RAMP[0];
  let upper = SCORE_RAMP[SCORE_RAMP.length - 1];
  for (let i = 1; i < SCORE_RAMP.length; i += 1) {
    if (position <= SCORE_RAMP[i].position) {
      lower = SCORE_RAMP[i - 1];
      upper = SCORE_RAMP[i];
      break;
    }
  }

  const span = upper.position - lower.position;
  const t = span === 0 ? 0 : (position - lower.position) / span;
  const l = lerp(lower.color.l, upper.color.l, t);
  const c = lerp(lower.color.c, upper.color.c, t);
  const h = lerp(lower.color.h, upper.color.h, t);

  return {
    background: `oklch(${trim(l, 4)} ${trim(c, 4)} ${trim(h, 2)})`,
    foreground: textColorForLightness(l),
  };
}
