/**
 * The slice of a game's timeline the transcript actually renders.
 *
 * A recorded game runs to hundreds of events, each of which mounts a row with
 * chips, a toggle and an actions menu, so rendering the whole timeline at once
 * costs far more than any one screen needs. The transcript therefore renders a
 * contiguous window over the loaded events and grows it as the user scrolls —
 * older events when they reach the top, newer ones when they reach the bottom.
 *
 * The window is expressed as half-open indices into the *filtered* primary
 * event list, not as seqs, so search filtering and a round jump both address it
 * the same way. Indices, not element identity, because the list they index is
 * rebuilt on every search keystroke.
 */
export interface TranscriptWindow {
  /** First rendered index, inclusive. */
  start: number;
  /** One past the last rendered index. */
  end: number;
}

/** How many events a freshly opened (or jumped-to) transcript renders. */
export const TRANSCRIPT_WINDOW_SIZE = 60;

/** How many more it renders each time the user scrolls to an edge. */
export const TRANSCRIPT_WINDOW_STEP = 40;

/**
 * The newest end of the timeline — where a transcript opens, because the last
 * thing that happened is what a reader wants first and it is what "Jump to
 * latest" returns to.
 */
export function tailWindow(
  total: number,
  size: number = TRANSCRIPT_WINDOW_SIZE
): TranscriptWindow {
  const end = Math.max(0, total);
  return { start: Math.max(0, end - Math.max(1, size)), end };
}

/** A window that begins at `index`, for jumping to a round or a single move. */
export function windowFrom(
  index: number,
  total: number,
  size: number = TRANSCRIPT_WINDOW_SIZE
): TranscriptWindow {
  const safeTotal = Math.max(0, total);
  const start = Math.min(Math.max(0, index), Math.max(0, safeTotal - 1));
  return { start, end: Math.min(safeTotal, start + Math.max(1, size)) };
}

/** Extend towards older events (upwards). */
export function extendOlder(
  window: TranscriptWindow,
  step: number = TRANSCRIPT_WINDOW_STEP
): TranscriptWindow {
  return { ...window, start: Math.max(0, window.start - Math.max(1, step)) };
}

/** Extend towards newer events (downwards), stopping at the end of the list. */
export function extendNewer(
  window: TranscriptWindow,
  total: number,
  step: number = TRANSCRIPT_WINDOW_STEP
): TranscriptWindow {
  return {
    ...window,
    end: Math.min(Math.max(0, total), window.end + Math.max(1, step)),
  };
}

/** True when nothing older than the window remains to be rendered. */
export function isAtOldest(window: TranscriptWindow): boolean {
  return window.start <= 0;
}

/** True when the window reaches the newest loaded event. */
export function isAtNewest(window: TranscriptWindow, total: number): boolean {
  return window.end >= Math.max(0, total);
}

/**
 * Re-fit a window to a list whose length changed — a search filter narrowing the
 * list, or live play appending to it.
 *
 * A window sitting at the newest end stays there, so a transcript following live
 * play keeps following it. Otherwise the window keeps its size and is pushed
 * inside the new bounds, so a reader parked mid-game is not yanked to the end by
 * an unrelated append.
 */
export function refitWindow(
  window: TranscriptWindow,
  previousTotal: number,
  total: number
): TranscriptWindow {
  const safeTotal = Math.max(0, total);
  if (safeTotal === 0) return { start: 0, end: 0 };
  // Never carry forward a window narrower than a screenful. A search that matched
  // nothing collapses the window to zero width, and clearing that search must
  // bring a full window back rather than a single row.
  const retained = Math.max(window.end - window.start, TRANSCRIPT_WINDOW_SIZE);
  if (isAtNewest(window, previousTotal)) {
    return tailWindow(safeTotal, retained);
  }
  const size = Math.min(retained, safeTotal);
  const start = Math.min(Math.max(0, window.start), safeTotal - size);
  return { start, end: start + size };
}

/**
 * Make sure `index` is rendered, extending the window rather than replacing it
 * when the target is only just outside — jumping a long way rebuilds the window
 * around the target instead, so the DOM does not grow without bound.
 */
export function windowContaining(
  window: TranscriptWindow,
  index: number,
  total: number,
  size: number = TRANSCRIPT_WINDOW_SIZE
): TranscriptWindow {
  const safeTotal = Math.max(0, total);
  if (safeTotal === 0) return { start: 0, end: 0 };
  const target = Math.min(Math.max(0, index), safeTotal - 1);
  if (target >= window.start && target < window.end) return window;
  const step = Math.max(1, size);
  if (target < window.start && window.start - target <= step) {
    return { ...window, start: target };
  }
  if (target >= window.end && target - window.end < step) {
    return { ...window, end: Math.min(safeTotal, target + 1) };
  }
  return windowFrom(target, safeTotal, size);
}
