import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import { PlayTranscript } from "@/features/play/components/play-transcript";
import { JobDetail, SessionDetail } from "@/features/shared/lib/types";

const selectedSession: SessionDetail = {
  id: "session-1",
  name: "Session",
  status: "active",
  context_recent_message_limit: null,
  context_recent_tool_exchange_limit: null,
  metadata: {},
  created_at: "2026-05-11T00:00:00Z",
  updated_at: "2026-05-11T00:00:00Z",
  terminated_at: null,
  model_config: null,
  skills: [],
  mcps: [],
  recent_job: null,
  recent_jobs: [],
};

function makeJob(text: string): JobDetail {
  return {
    id: "job-1",
    prompt: "Prompt",
    metadata: {},
    status: "running",
    attempts: 1,
    max_attempts: 1,
    error_code: null,
    error_message: null,
    result_text: null,
    cancellation_requested_at: null,
    created_at: "2026-05-11T00:00:00Z",
    started_at: "2026-05-11T00:00:01Z",
    completed_at: null,
    latest_event_id: "1",
    latest_event_type: "model_output",
    outputs: [],
    events: [
      {
        id: "1",
        event_type: "model_output",
        payload: { text },
        created_at: "2026-05-11T00:00:01Z",
      },
    ],
    available_tools: [],
  };
}

/** Scroll geometry: how far the viewport sits from the bottom, in pixels. */
function setDistanceFromBottom(el: HTMLElement, distance: number) {
  Object.defineProperty(el, "scrollHeight", {
    configurable: true,
    value: 1000,
  });
  Object.defineProperty(el, "clientHeight", { configurable: true, value: 200 });
  Object.defineProperty(el, "scrollTop", {
    configurable: true,
    value: 1000 - 200 - distance,
  });
}

/**
 * Fire an upward wheel and then move the reported geometry away from the bottom,
 * the way a browser would once it applies the scroll.
 */
function wheelUp(el: HTMLElement) {
  fireEvent.wheel(el, { deltaY: -120 });
  setDistanceFromBottom(el, 400);
}

function getScrollContainer(): HTMLElement {
  const el = document.querySelector<HTMLElement>(".overflow-y-auto");
  if (!el) {
    throw new Error("scroll container not found");
  }
  return el;
}

const scrollToSpy = vi.fn();

/**
 * jsdom has no ResizeObserver. The transcript uses one to notice content that
 * shrank below one viewport, so stand one in that the test can fire by hand.
 */
let resizeCallbacks: ResizeObserverCallback[] = [];

function installResizeObserverStub() {
  resizeCallbacks = [];
  Object.defineProperty(globalThis, "ResizeObserver", {
    configurable: true,
    writable: true,
    value: class {
      constructor(callback: ResizeObserverCallback) {
        resizeCallbacks.push(callback);
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  });
}

/** Report that the transcript content changed size. */
function triggerContentResize() {
  act(() => {
    for (const callback of resizeCallbacks) {
      callback([], {} as ResizeObserver);
    }
  });
}

function renderTranscript(jobs: JobDetail[], streaming = true) {
  return render(
    <PlayTranscript
      jobs={jobs}
      streamingJobId={streaming ? "job-1" : null}
      selectedSession={selectedSession}
      streamState={streaming ? "streaming" : "idle"}
      statusText="Ready"
      isBusy={false}
      errorText={null}
      onOpenSettings={vi.fn()}
      settingsOpen={false}
    />
  );
}

describe("PlayTranscript follow lock", () => {
  let now = 1000;

  beforeEach(() => {
    now = 1000;
    vi.spyOn(Date, "now").mockImplementation(() => now);
    installResizeObserverStub();
    scrollToSpy.mockClear();
    // jsdom implements neither; the component uses scrollTo when present.
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      writable: true,
      value: scrollToSpy,
    });
    HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("follows new output by default, with no re-engage control offered", () => {
    renderTranscript([makeJob("first")]);

    expect(scrollToSpy).toHaveBeenCalledWith(
      expect.objectContaining({ behavior: "smooth" })
    );
    expect(screen.queryByTestId("jump-to-latest")).toBeNull();
  });

  it("releases the lock on an upward wheel even while output is streaming", () => {
    const { rerender } = renderTranscript([makeJob("first")]);
    const container = getScrollContainer();

    // Streaming keeps re-arming the programmatic-scroll guard, so a plain scroll
    // event is ignored — the wheel gesture must release the lock regardless.
    fireEvent.scroll(container);
    expect(screen.queryByTestId("jump-to-latest")).toBeNull();

    wheelUp(container);

    expect(screen.getByTestId("jump-to-latest")).toBeInTheDocument();

    // Further tokens must not drag the viewport back down.
    scrollToSpy.mockClear();
    rerender(
      <PlayTranscript
        jobs={[makeJob("first and more")]}
        streamingJobId="job-1"
        selectedSession={selectedSession}
        streamState="streaming"
        statusText="Ready"
        isBusy={false}
        errorText={null}
        onOpenSettings={vi.fn()}
        settingsOpen={false}
      />
    );
    expect(scrollToSpy).not.toHaveBeenCalledWith(
      expect.objectContaining({ behavior: "smooth" })
    );
  });

  it("ignores a downward wheel, which is not a move away from the newest output", () => {
    renderTranscript([makeJob("first")]);
    const container = getScrollContainer();

    fireEvent.wheel(container, { deltaY: 120 });

    expect(screen.queryByTestId("jump-to-latest")).toBeNull();
  });

  it.each(["ArrowUp", "PageUp", "Home"])(
    "releases the lock when %s scrolls the transcript upwards",
    (key) => {
      renderTranscript([makeJob("first")]);

      const container = getScrollContainer();
      fireEvent.keyDown(container, { key });
      setDistanceFromBottom(container, 400);

      expect(screen.getByTestId("jump-to-latest")).toBeInTheDocument();
    }
  );

  it("keeps following when an unrelated key is pressed", () => {
    renderTranscript([makeJob("first")]);

    fireEvent.keyDown(getScrollContainer(), { key: "ArrowDown" });

    expect(screen.queryByTestId("jump-to-latest")).toBeNull();
  });

  it("releases the lock when a touch drag pulls the content down", () => {
    renderTranscript([makeJob("first")]);
    const container = getScrollContainer();

    fireEvent.touchStart(container, { touches: [{ clientY: 100 }] });
    fireEvent.touchMove(container, { touches: [{ clientY: 60 }] });
    // Dragging upwards scrolls towards the newest output: still following.
    expect(screen.queryByTestId("jump-to-latest")).toBeNull();

    fireEvent.touchMove(container, { touches: [{ clientY: 180 }] });
    setDistanceFromBottom(container, 400);

    expect(screen.getByTestId("jump-to-latest")).toBeInTheDocument();
  });

  it("re-engages when the user scrolls back to the bottom", () => {
    renderTranscript([makeJob("first")]);
    const container = getScrollContainer();

    wheelUp(container);
    fireEvent.scroll(container);
    expect(screen.getByTestId("jump-to-latest")).toBeInTheDocument();

    // Landing back at the bottom re-arms the follow, terminal-style.
    setDistanceFromBottom(container, 0);
    fireEvent.scroll(container);

    expect(screen.queryByTestId("jump-to-latest")).toBeNull();
  });

  it("stays released while the viewport is merely near the bottom", () => {
    renderTranscript([makeJob("first")]);
    const container = getScrollContainer();

    wheelUp(container);
    setDistanceFromBottom(container, 60);
    fireEvent.scroll(container);

    expect(screen.getByTestId("jump-to-latest")).toBeInTheDocument();
  });

  it("follows content that grows after the last job update", () => {
    renderTranscript([makeJob("first")]);
    const container = getScrollContainer();

    // Markdown finishing its layout moves the bottom away without any new job.
    setDistanceFromBottom(container, 85);
    scrollToSpy.mockClear();
    triggerContentResize();

    expect(scrollToSpy).toHaveBeenCalledWith(
      expect.objectContaining({ behavior: "smooth" })
    );
    expect(screen.queryByTestId("jump-to-latest")).toBeNull();
  });

  it("does not re-scroll on a resize that leaves the viewport at the bottom", () => {
    renderTranscript([makeJob("first")]);
    const container = getScrollContainer();

    setDistanceFromBottom(container, 0);
    scrollToSpy.mockClear();
    triggerContentResize();

    expect(scrollToSpy).not.toHaveBeenCalled();
  });

  it("re-engages when the content shrinks until nothing can scroll", () => {
    renderTranscript([makeJob("first")]);
    const container = getScrollContainer();

    wheelUp(container);
    expect(screen.getByTestId("jump-to-latest")).toBeInTheDocument();

    // The transcript now fits the viewport, so there is nowhere to scroll to and
    // the control must not linger.
    setDistanceFromBottom(container, 0);
    triggerContentResize();

    expect(screen.queryByTestId("jump-to-latest")).toBeNull();
  });

  it("stays released while the user is scrolled up, even as content resizes", () => {
    renderTranscript([makeJob("first")]);
    const container = getScrollContainer();

    wheelUp(container);
    triggerContentResize();

    expect(screen.getByTestId("jump-to-latest")).toBeInTheDocument();
  });

  it("re-engages and scrolls to the bottom when the follow control is pressed", () => {
    renderTranscript([makeJob("first")]);
    const container = getScrollContainer();

    wheelUp(container);
    fireEvent.scroll(container);
    scrollToSpy.mockClear();

    fireEvent.click(screen.getByTestId("jump-to-latest"));

    expect(screen.queryByTestId("jump-to-latest")).toBeNull();
    expect(scrollToSpy).toHaveBeenCalledWith(
      expect.objectContaining({ behavior: "smooth" })
    );
  });

  it("keeps the lock through the programmatic scroll it starts", () => {
    renderTranscript([makeJob("first")]);
    const container = getScrollContainer();

    wheelUp(container);
    fireEvent.scroll(container);
    fireEvent.click(screen.getByTestId("jump-to-latest"));

    // A scroll event fired mid-animation, still far from the bottom, must not
    // release the freshly engaged lock.
    now += 100;
    fireEvent.scroll(container);

    expect(screen.queryByTestId("jump-to-latest")).toBeNull();
  });
});
