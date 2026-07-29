import "@testing-library/jest-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { SubagentList } from "@/features/play/components/subagent-list";
import { SubagentEntry } from "@/features/play/lib/play-session-events";

class StubEventSource {
  static instances: StubEventSource[] = [];
  onerror: (() => void) | null = null;

  constructor(public readonly url: string) {
    StubEventSource.instances.push(this);
  }

  addEventListener() {}

  close() {}
}

function entry(
  index: number,
  status: SubagentEntry["status"],
  name?: string
): SubagentEntry {
  return {
    childJobId: `child-job-${index}`,
    childSessionId: `child-session-${index}`,
    status,
    ...(name === undefined ? {} : { name }),
  };
}

function renderList(entries: SubagentEntry[], onSelect = vi.fn()) {
  const view = render(<SubagentList entries={entries} onSelect={onSelect} />);
  return { ...view, onSelect };
}

function expand() {
  fireEvent.click(screen.getByLabelText("Expand subagents"));
}

beforeEach(() => {
  StubEventSource.instances = [];
  Object.defineProperty(globalThis, "EventSource", {
    configurable: true,
    value: StubEventSource,
  });
});

describe("SubagentList container", () => {
  it("renders nothing when there are no subagents", () => {
    const { container } = renderList([]);
    expect(container).toBeEmptyDOMElement();
  });

  it("keeps the entries in a bounded, self-scrolling box", () => {
    renderList([
      entry(1, "completed"),
      entry(2, "completed"),
      entry(3, "running"),
    ]);
    expand();

    const scroller = screen.getByTestId("subagent-list-scroll");
    // Bounded: the box has a height cap, so a long list cannot grow the page.
    expect(scroller.className).toContain("max-h-[min(45vh,16rem)]");
    // Scrollable: the overflow is the box's own, not the document's.
    expect(scroller.className).toContain("overflow-y-auto");
    expect(scroller.className).toContain("overscroll-contain");
  });

  it("keeps every entry inside the scrolling box rather than beside it", () => {
    const entries = Array.from({ length: 30 }, (_, index) =>
      entry(index, "completed", `Agent ${index}`)
    );
    renderList(entries);
    expand();

    const scroller = screen.getByTestId("subagent-list-scroll");
    for (const item of entries) {
      expect(
        within(scroller).getByText(item.name as string)
      ).toBeInTheDocument();
    }
  });

  it("shows only running and failed subagents while collapsed", () => {
    renderList([
      entry(1, "completed", "Done one"),
      entry(2, "running", "Live one"),
      entry(3, "failed", "Broken one"),
    ]);

    expect(screen.getByText("Live one")).toBeInTheDocument();
    expect(screen.getByText("Broken one")).toBeInTheDocument();
    expect(screen.queryByText("Done one")).toBeNull();
    expect(screen.getByText("1 failed")).toBeInTheDocument();
  });

  it("falls back to a short job id when an entry has no name", () => {
    renderList([entry(1, "running")]);
    expect(screen.getByText("child-jo")).toBeInTheDocument();
  });

  it("redacts a credential in a name recorded before names were generated", () => {
    // Names used to be `prompt.slice(0, 50)`, and stored events are replayed for
    // as long as the session exists.
    renderList([
      entry(1, "running", "curl -H authorization: Bearer sk-live-abc"),
    ]);

    expect(screen.queryByText(/sk-live-abc/)).toBeNull();
    expect(screen.getByText(/REDACTED/)).toBeInTheDocument();
  });

  it("opens the selected subagent", () => {
    const { onSelect } = renderList([entry(1, "running", "Live one")]);
    fireEvent.click(screen.getByText("Live one"));
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ childJobId: "child-job-1" })
    );
  });
});

describe("SubagentList status filter", () => {
  const entries = [
    entry(1, "completed", "Done one"),
    entry(2, "completed", "Done two"),
    entry(3, "running", "Live one"),
    entry(4, "failed", "Broken one"),
  ];

  it("is offered only once the list is expanded", () => {
    renderList(entries);
    expect(screen.queryByTestId("subagent-status-filter")).toBeNull();
    expand();
    expect(screen.getByTestId("subagent-status-filter")).toBeInTheDocument();
  });

  it("labels each status with how many subagents it holds", () => {
    renderList(entries);
    expand();

    const filter = screen.getByTestId("subagent-status-filter");
    expect(within(filter).getByText("All 4")).toBeInTheDocument();
    expect(within(filter).getByText("Live 1")).toBeInTheDocument();
    expect(within(filter).getByText("Done 2")).toBeInTheDocument();
    expect(within(filter).getByText("Failed 1")).toBeInTheDocument();
  });

  it("shows every subagent by default", () => {
    renderList(entries);
    expand();

    for (const name of ["Done one", "Done two", "Live one", "Broken one"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
  });

  it("narrows the list to the chosen status", () => {
    renderList(entries);
    expand();

    fireEvent.click(screen.getByText("Failed 1"));

    expect(screen.getByText("Broken one")).toBeInTheDocument();
    expect(screen.queryByText("Done one")).toBeNull();
    expect(screen.queryByText("Live one")).toBeNull();
  });

  it("hides finished subagents when the reader asks for the live ones", () => {
    renderList(entries);
    expand();

    fireEvent.click(screen.getByText("Live 1"));

    expect(screen.getByText("Live one")).toBeInTheDocument();
    expect(screen.queryByText("Done one")).toBeNull();
    expect(screen.queryByText("Done two")).toBeNull();
    expect(screen.queryByText("Broken one")).toBeNull();
  });

  it("returns to the whole list when the reader picks All again", () => {
    renderList(entries);
    expand();

    fireEvent.click(screen.getByText("Failed 1"));
    fireEvent.click(screen.getByText("All 4"));

    expect(screen.getByText("Done one")).toBeInTheDocument();
    expect(screen.getByText("Live one")).toBeInTheDocument();
  });

  it("says so when the chosen status holds nothing", () => {
    renderList([entry(1, "completed", "Done one")]);
    expand();

    fireEvent.click(screen.getByText("Failed 0"));

    expect(screen.getByTestId("subagent-list-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("subagent-list-scroll")).toBeNull();
  });
});
