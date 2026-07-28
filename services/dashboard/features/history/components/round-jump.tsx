"use client";

import { ListBox, ListBoxItem, Select } from "@heroui/react";

import { NavRound } from "@/features/history/lib/history-rounds";

/**
 * Jump the transcript straight to a round.
 *
 * A played-out game is hundreds of events across a dozen or more rounds, and the
 * transcript renders a window over them rather than all of them, so scrolling is
 * no longer a way to reach round 2 of 15. Picking a round here selects that
 * round's first move, which is what moves the transcript's window and scrolls it
 * into view.
 *
 * The option list is the same round breakdown the sidebar navigation tree is
 * built from, so both name rounds identically ("Setup", then "Round N" using
 * DragnCards' completed-round convention).
 */
export function RoundJump({
  rounds,
  onJump,
}: {
  rounds: NavRound[];
  /** Called with the `seq` of the chosen round's first move. */
  onJump: (seq: number) => void;
}) {
  const jumpable = rounds.filter((round) => round.moves.length > 0);
  if (jumpable.length === 0) return null;

  return (
    // Left unselected by design: this is an action, not a stored setting, so
    // picking the same round twice jumps twice instead of doing nothing.
    <Select
      aria-label="Jump to round"
      value={null}
      onChange={(nextValue) => {
        if (nextValue == null) return;
        const round = jumpable.find((r) => r.key === String(nextValue));
        if (round) onJump(round.moves[0].seq);
      }}
    >
      <Select.Trigger
        aria-label="Jump to round"
        data-testid="history-round-jump"
        className="w-36 shrink-0"
      >
        <Select.Value>Jump to round</Select.Value>
        <Select.Indicator />
      </Select.Trigger>
      <Select.Popover>
        <ListBox aria-label="Rounds">
          {jumpable.map((round) => (
            <ListBoxItem
              key={round.key}
              id={round.key}
              data-testid={`history-round-jump-${round.key}`}
              textValue={round.label}
            >
              {round.label}
            </ListBoxItem>
          ))}
        </ListBox>
      </Select.Popover>
    </Select>
  );
}
