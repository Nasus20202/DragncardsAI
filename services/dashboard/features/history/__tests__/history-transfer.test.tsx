import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import { HistoryTransferControls } from "@/features/history/components/history-transfer";
import {
  historyExportUrl,
  importHistoryBundle,
} from "@/features/history/lib/history-api";

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    statusText: ok ? "OK" : "Error",
    json: async () => body,
  } as unknown as Response;
}

function bundleFile(name = "game.ndjson"): File {
  return new File(['{"kind":"header"}\n'], name, {
    type: "application/x-ndjson",
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("history bundle API client", () => {
  it("builds an encoded export URL through the history proxy", () => {
    expect(historyExportUrl("game 1/../x")).toBe(
      "/api/proxy/history/games/game%201%2F..%2Fx/export"
    );
  });

  it("posts the picked file as the import body", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ game_id: "g1", imported_events: 3 }));
    vi.stubGlobal("fetch", fetchMock);

    const file = bundleFile();
    const result = await importHistoryBundle(file);

    expect(fetchMock).toHaveBeenCalledWith("/api/proxy/history/import", {
      method: "POST",
      headers: { "content-type": "application/x-ndjson" },
      body: file,
    });
    expect(result.game_id).toBe("g1");
  });

  it("passes an explicit target game id as a query param", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ game_id: "t" }));
    vi.stubGlobal("fetch", fetchMock);

    await importHistoryBundle(bundleFile(), { gameId: "t copy" });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/proxy/history/import?game_id=t+copy"
    );
  });

  it("surfaces the service's detail message on a rejected bundle", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse({ detail: "line 4: not valid JSON" }, false, 400)
        )
    );

    await expect(importHistoryBundle(bundleFile())).rejects.toThrow(
      "line 4: not valid JSON"
    );
  });
});

describe("HistoryTransferControls", () => {
  it("downloads the selected game's bundle from the export endpoint", () => {
    const clicked: string[] = [];
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        clicked.push(this.getAttribute("href") ?? "");
      });

    render(
      <HistoryTransferControls
        gameId="g1"
        onNotice={vi.fn()}
        onImported={vi.fn()}
      />
    );
    fireEvent.click(screen.getByTestId("history-export"));

    expect(clickSpy).toHaveBeenCalledOnce();
    expect(clicked).toEqual(["/api/proxy/history/games/g1/export"]);
    // The anchor is not left behind in the document.
    expect(document.querySelector("a[download]")).toBeNull();
  });

  it("offers no export when no game is selected, but still offers import", () => {
    render(
      <HistoryTransferControls
        gameId={null}
        onNotice={vi.fn()}
        onImported={vi.fn()}
      />
    );

    expect(screen.queryByTestId("history-export")).not.toBeInTheDocument();
    expect(screen.getByTestId("history-import")).toBeInTheDocument();
  });

  it("reports what an accepted import wrote and selects the new game", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          game_id: "restored",
          source_game_id: "g1",
          imported_events: 12,
          imported_snapshots: 2,
        })
      )
    );
    const onNotice = vi.fn();
    const onImported = vi.fn();

    render(
      <HistoryTransferControls
        gameId={null}
        onNotice={onNotice}
        onImported={onImported}
      />
    );
    fireEvent.change(screen.getByTestId("history-import-input"), {
      target: { files: [bundleFile()] },
    });

    await waitFor(() => {
      expect(onImported).toHaveBeenCalledWith("restored");
    });
    expect(onNotice).toHaveBeenCalledWith({
      kind: "success",
      message:
        "Imported 12 events and 2 snapshots into restored (exported as g1).",
    });
  });

  it("reports a rejected bundle as a failure without selecting anything", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            { detail: "line 7: footer declares 9 events but 8 were read" },
            false,
            400
          )
        )
    );
    const onNotice = vi.fn();
    const onImported = vi.fn();

    render(
      <HistoryTransferControls
        gameId="g1"
        onNotice={onNotice}
        onImported={onImported}
      />
    );
    fireEvent.change(screen.getByTestId("history-import-input"), {
      target: { files: [bundleFile()] },
    });

    await waitFor(() => {
      expect(onNotice).toHaveBeenCalledWith({
        kind: "failure",
        message: "line 7: footer declares 9 events but 8 were read",
      });
    });
    expect(onImported).not.toHaveBeenCalled();
  });

  it("only accepts bundle files", () => {
    render(
      <HistoryTransferControls
        gameId="g1"
        onNotice={vi.fn()}
        onImported={vi.fn()}
      />
    );

    expect(screen.getByTestId("history-import-input")).toHaveAttribute(
      "accept",
      ".ndjson,.jsonl,application/x-ndjson"
    );
  });
});
