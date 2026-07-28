import { describe, expect, it } from "vitest";

import {
  TRANSCRIPT_WINDOW_SIZE,
  extendNewer,
  extendOlder,
  isAtNewest,
  isAtOldest,
  refitWindow,
  tailWindow,
  windowContaining,
  windowFrom,
} from "@/features/history/lib/transcript-window";

describe("tailWindow", () => {
  it("opens at the newest end of a long timeline", () => {
    expect(tailWindow(500, 60)).toEqual({ start: 440, end: 500 });
    expect(isAtNewest(tailWindow(500, 60), 500)).toBe(true);
    expect(isAtOldest(tailWindow(500, 60))).toBe(false);
  });

  it("covers a timeline shorter than one window whole", () => {
    expect(tailWindow(12, 60)).toEqual({ start: 0, end: 12 });
    expect(isAtOldest(tailWindow(12, 60))).toBe(true);
  });

  it("is empty for an empty timeline", () => {
    expect(tailWindow(0, 60)).toEqual({ start: 0, end: 0 });
  });
});

describe("extendOlder / extendNewer", () => {
  it("grows upwards and stops at the first event", () => {
    expect(extendOlder({ start: 100, end: 160 }, 40)).toEqual({
      start: 60,
      end: 160,
    });
    expect(extendOlder({ start: 10, end: 70 }, 40)).toEqual({
      start: 0,
      end: 70,
    });
    expect(isAtOldest(extendOlder({ start: 10, end: 70 }, 40))).toBe(true);
  });

  it("grows downwards and stops at the last loaded event", () => {
    expect(extendNewer({ start: 0, end: 60 }, 500, 40)).toEqual({
      start: 0,
      end: 100,
    });
    expect(extendNewer({ start: 0, end: 60 }, 80, 40)).toEqual({
      start: 0,
      end: 80,
    });
    expect(isAtNewest(extendNewer({ start: 0, end: 60 }, 80, 40), 80)).toBe(
      true
    );
  });
});

describe("windowFrom", () => {
  it("starts at the requested index", () => {
    expect(windowFrom(120, 500, 60)).toEqual({ start: 120, end: 180 });
  });

  it("clamps a start past the end of the list", () => {
    expect(windowFrom(900, 500, 60)).toEqual({ start: 499, end: 500 });
  });

  it("clamps a negative index to the beginning", () => {
    expect(windowFrom(-5, 500, 60)).toEqual({ start: 0, end: 60 });
  });
});

describe("refitWindow", () => {
  it("keeps a window that was following live play at the newest end", () => {
    // 500 events, window at the tail, three more get appended.
    const followed = refitWindow({ start: 440, end: 500 }, 500, 503);
    expect(followed).toEqual({ start: 443, end: 503 });
    expect(isAtNewest(followed, 503)).toBe(true);
  });

  it("leaves a reader parked mid-game where they were", () => {
    const parked = refitWindow({ start: 100, end: 160 }, 500, 503);
    expect(parked).toEqual({ start: 100, end: 160 });
  });

  it("restores a full window after a search that matched nothing", () => {
    // The zero-match window collapses to zero width; clearing the search must
    // not leave a one-row transcript behind.
    const collapsed = refitWindow({ start: 440, end: 500 }, 500, 0);
    expect(collapsed).toEqual({ start: 0, end: 0 });
    const restored = refitWindow(collapsed, 0, 3);
    expect(restored).toEqual({ start: 0, end: 3 });
  });

  it("pulls a window back inside a list that shrank under it", () => {
    const narrowed = refitWindow({ start: 400, end: 460 }, 500, 80);
    expect(narrowed).toEqual({ start: 20, end: 80 });
  });
});

describe("windowContaining", () => {
  it("leaves a window that already renders the target alone", () => {
    const current = { start: 100, end: 160 };
    expect(windowContaining(current, 130, 500, 60)).toBe(current);
  });

  it("stretches to reach a target just above the window", () => {
    // Nearby: extend rather than replace, so the surrounding context stays.
    expect(windowContaining({ start: 100, end: 160 }, 80, 500, 60)).toEqual({
      start: 80,
      end: 160,
    });
  });

  it("stretches to reach a target just below the window", () => {
    expect(windowContaining({ start: 100, end: 160 }, 170, 500, 60)).toEqual({
      start: 100,
      end: 171,
    });
  });

  it("rebuilds around a distant target instead of spanning the gap", () => {
    // Jumping from round 15 back to round 1 must not render everything between.
    expect(windowContaining({ start: 440, end: 500 }, 5, 500, 60)).toEqual({
      start: 5,
      end: 65,
    });
  });

  it("is empty for an empty list", () => {
    expect(windowContaining({ start: 0, end: 0 }, 3, 0, 60)).toEqual({
      start: 0,
      end: 0,
    });
  });

  it("uses a screenful by default", () => {
    expect(windowContaining({ start: 0, end: 1 }, 400, 500)).toEqual({
      start: 400,
      end: 400 + TRANSCRIPT_WINDOW_SIZE,
    });
  });
});
