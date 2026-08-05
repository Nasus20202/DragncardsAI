"use client";

import { Chip } from "@heroui/react";
import type { CSSProperties } from "react";

import { formatScore } from "@/features/history/lib/history-rounds";
import { scoreColors } from "@/features/history/lib/score-colors";

/**
 * An evaluation's overall score, shown in a colour derived from the score.
 *
 * Every place the dashboard shows an overall score renders this, so the same
 * number cannot end up two different colours: the per-verdict chip in a move's
 * evaluation list, the latest-score indicator on a graded move, and each cell of
 * the per-player scorecard.
 *
 * Renders nothing when there is no score to show, and falls back to the neutral
 * chip colour for a value `scoreColors` cannot place on the ramp — never to the
 * colour of a top score.
 */
export function ScoreChip({
  value,
  testId,
}: {
  /** The overall score, on the 0–10 scale. */
  value: number | null | undefined;
  testId?: string;
}) {
  const label = formatScore(value);
  if (!label) return null;

  const colors = scoreColors(value);
  const style: CSSProperties | undefined = colors
    ? { backgroundColor: colors.background, color: colors.foreground }
    : undefined;

  return (
    <Chip size="sm" variant="primary" style={style} data-testid={testId}>
      {label}
    </Chip>
  );
}
