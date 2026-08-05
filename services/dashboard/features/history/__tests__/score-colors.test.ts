import { describe, expect, it } from "vitest";

import {
  DARK_TEXT,
  LIGHT_TEXT,
  SCORE_MAX,
  SCORE_MIN,
  scoreColors,
  textColorForLightness,
} from "@/features/history/lib/score-colors";

/** Pull the three OKLCH components out of an `oklch(l c h)` string. */
function parts(background: string): { l: number; c: number; h: number } {
  const match = background.match(/^oklch\((-?[\d.]+) (-?[\d.]+) (-?[\d.]+)\)$/);
  expect(match, `unparseable background: ${background}`).not.toBeNull();
  const [, l, c, h] = match as RegExpMatchArray;
  return { l: Number(l), c: Number(c), h: Number(h) };
}

function background(value: number): string {
  const colors = scoreColors(value);
  expect(colors).not.toBeNull();
  return colors!.background;
}

describe("scoreColors", () => {
  it("puts Hero UI's danger red at the bottom of the scale", () => {
    // --danger: oklch(0.6532 0.2328 25.74)
    expect(background(SCORE_MIN)).toBe("oklch(0.6532 0.2328 25.74)");
  });

  it("puts Hero UI's success green at the top of the scale", () => {
    // --success: oklch(0.7329 0.1935 150.81)
    expect(background(SCORE_MAX)).toBe("oklch(0.7329 0.1935 150.81)");
  });

  it("puts Hero UI's warning amber at the midpoint, not a brown blend", () => {
    // --warning: oklch(0.7819 0.1585 72.33)
    expect(background(5)).toBe("oklch(0.7819 0.1585 72.33)");

    // An amber, i.e. between the red and green hues and well clear of both, and
    // still saturated — a muddy midpoint would show up as collapsed chroma.
    const mid = parts(background(5));
    expect(mid.h).toBeGreaterThan(parts(background(SCORE_MIN)).h + 20);
    expect(mid.h).toBeLessThan(parts(background(SCORE_MAX)).h - 20);
    expect(mid.c).toBeGreaterThan(0.12);
  });

  it("never loses chroma anywhere along the ramp", () => {
    for (let score = 0; score <= 10; score += 0.25) {
      expect(parts(background(score)).c).toBeGreaterThan(0.12);
    }
  });

  it("rotates hue monotonically from red to green", () => {
    let previous = -Infinity;
    for (let score = 0; score <= 10; score += 0.5) {
      const { h } = parts(background(score));
      expect(h).toBeGreaterThan(previous);
      previous = h;
    }
  });

  it("distinguishes fractional scores a tenth of a point apart", () => {
    // The scorecard colours an average, so 7.4 and 7.6 must not collapse onto
    // one colour the way a banded scale would collapse them.
    expect(background(7.4)).not.toBe(background(7.6));
  });

  it("is a pure function of the score", () => {
    expect(scoreColors(6.3)).toEqual(scoreColors(6.3));
  });

  it("gives no colour to a score that cannot be placed on the ramp", () => {
    expect(scoreColors(null)).toBeNull();
    expect(scoreColors(undefined)).toBeNull();
    expect(scoreColors(Number.NaN)).toBeNull();
    expect(scoreColors(Number.POSITIVE_INFINITY)).toBeNull();
    expect(scoreColors(Number.NEGATIVE_INFINITY)).toBeNull();
    expect(scoreColors("8" as unknown as number)).toBeNull();
  });

  it("clamps a finite out-of-range score to the nearer end", () => {
    expect(background(-5)).toBe(background(SCORE_MIN));
    expect(background(42)).toBe(background(SCORE_MAX));
  });

  it("keeps the text legible everywhere on the ramp", () => {
    for (let score = 0; score <= 10; score += 0.5) {
      const colors = scoreColors(score);
      expect(colors).not.toBeNull();
      // The foreground follows the computed background's lightness, and every
      // stop of the ramp is light enough that near-black text wins — so the
      // number does not flip colour part-way along the ramp.
      expect(colors!.foreground).toBe(
        textColorForLightness(parts(colors!.background).l)
      );
      expect(colors!.foreground).toBe(DARK_TEXT);
    }
  });
});

describe("textColorForLightness", () => {
  it("takes near-black text on a light background", () => {
    expect(textColorForLightness(0.9)).toBe(DARK_TEXT);
    expect(textColorForLightness(0.63)).toBe(DARK_TEXT);
  });

  it("takes near-white text on a dark background", () => {
    // Not reachable from the ramp's current stops, but the rule is applied to
    // the computed background rather than assumed, so a darkened stop would
    // still be given legible text.
    expect(textColorForLightness(0.62)).toBe(LIGHT_TEXT);
    expect(textColorForLightness(0.2)).toBe(LIGHT_TEXT);
  });
});
