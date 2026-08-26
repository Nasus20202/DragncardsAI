import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import { HistoryTransferControls } from "@/features/history/components/history-transfer";
import {
  historyExportFilename,
  historyExportUrl,
  importHistoryBundle,
} from "@/features/history/lib/history-api";
import { installResizeObserver } from "@/features/shared/__tests__/heroui-test-env";

beforeAll(installResizeObserver);

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

/** An accepted import, with the two fields the notice row reads defaulted. */
function importResult(overrides: Record<string, unknown> = {}) {
  return {
    game_id: "g1",
    platform: "dragncards" as const,
    source_game_id: "g1",
    imported_events: 12,
    imported_snapshots: 2,
    mode: "full",
    source_id_references: 0,
    ...overrides,
  };
}

/** Picks a bundle and answers the target dialog it opens. */
function pickBundle(
  target: "new" | "bundle" | "custom" = "new",
  customId?: string
) {
  fireEvent.change(screen.getByTestId("history-import-input"), {
    target: { files: [bundleFile()] },
  });
  fireEvent.click(screen.getByTestId(`history-import-target-${target}`));
  if (customId !== undefined) {
    fireEvent.change(screen.getByTestId("history-import-game-id"), {
      target: { value: customId },
    });
  }
  fireEvent.click(screen.getByTestId("history-import-confirm"));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("history bundle API client", () => {
  it("builds an encoded export URL through the history proxy", () => {
    expect(historyExportUrl("game 1/../x")).toBe(
      "/api/proxy/history/games/game%201%2F..%2Fx/export?mode=full"
    );
  });

  it("asks for the mode it was given rather than the server's default", () => {
    expect(historyExportUrl("g1", "minimal")).toBe(
      "/api/proxy/history/games/g1/export?mode=minimal"
    );
  });

  it("includes the Marvel LCG partition on an export URL", () => {
    expect(historyExportUrl("g1", "full", "marvel-lcg")).toBe(
      "/api/proxy/history/games/g1/export?mode=full&platform=marvel-lcg"
    );
  });

  it("names the download the way the service's own header does", () => {
    expect(historyExportFilename("g1")).toBe(
      "dragncards-history-g1-full.ndjson"
    );
    expect(historyExportFilename("g1", "minimal")).toBe(
      "dragncards-history-g1-minimal.ndjson"
    );
  });

  it("posts the picked file as the import body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(importResult()));
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
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(importResult()));
    vi.stubGlobal("fetch", fetchMock);

    await importHistoryBundle(bundleFile(), { gameId: "t copy" });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/proxy/history/import?game_id=t+copy"
    );
  });

  it("asks the service to mint an id when told to import as new", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(importResult()));
    vi.stubGlobal("fetch", fetchMock);

    await importHistoryBundle(bundleFile(), { asNew: true });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/proxy/history/import?as_new=true"
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
  it("downloads the mode chosen in the export dialog", async () => {
    const downloads: { href: string; name: string }[] = [];
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        downloads.push({
          href: this.getAttribute("href") ?? "",
          name: this.getAttribute("download") ?? "",
        });
      });

    render(
      <HistoryTransferControls
        gameId="g1"
        onNotice={vi.fn()}
        onImported={vi.fn()}
      />
    );
    fireEvent.click(screen.getByTestId("history-export"));
    fireEvent.click(await screen.findByTestId("history-export-mode-minimal"));
    fireEvent.click(screen.getByTestId("history-export-confirm"));

    expect(clickSpy).toHaveBeenCalledOnce();
    expect(downloads).toEqual([
      {
        href: "/api/proxy/history/games/g1/export?mode=minimal",
        name: "dragncards-history-g1-minimal.ndjson",
      },
    ]);
    // The anchor is not left behind in the document.
    expect(document.querySelector("a[download]")).toBeNull();
  });

  it("exports the lossless bundle when the dialog is confirmed unchanged", async () => {
    const downloads: { href: string; name: string }[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement
    ) {
      downloads.push({
        href: this.getAttribute("href") ?? "",
        name: this.getAttribute("download") ?? "",
      });
    });

    render(
      <HistoryTransferControls
        gameId="g1"
        onNotice={vi.fn()}
        onImported={vi.fn()}
      />
    );
    fireEvent.click(screen.getByTestId("history-export"));
    fireEvent.click(await screen.findByTestId("history-export-confirm"));

    expect(downloads).toEqual([
      {
        href: "/api/proxy/history/games/g1/export?mode=full",
        name: "dragncards-history-g1-full.ndjson",
      },
    ]);
  });

  it("exports the selected Marvel LCG partition", async () => {
    const downloads: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
      this: HTMLAnchorElement
    ) {
      downloads.push(this.getAttribute("href") ?? "");
    });

    render(
      <HistoryTransferControls
        gameId="marvel-game"
        platform="marvel-lcg"
        onNotice={vi.fn()}
        onImported={vi.fn()}
      />
    );
    fireEvent.click(screen.getByTestId("history-export"));
    fireEvent.click(await screen.findByTestId("history-export-confirm"));

    expect(downloads).toEqual([
      "/api/proxy/history/games/marvel-game/export?mode=full&platform=marvel-lcg",
    ]);
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

  it("imports under a freshly minted id by default", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(importResult({ game_id: "minted", source_game_id: "g1" }))
      );
    vi.stubGlobal("fetch", fetchMock);
    const onImported = vi.fn();

    render(
      <HistoryTransferControls
        gameId={null}
        onNotice={vi.fn()}
        onImported={onImported}
      />
    );
    fireEvent.change(screen.getByTestId("history-import-input"), {
      target: { files: [bundleFile()] },
    });
    fireEvent.click(await screen.findByTestId("history-import-confirm"));

    await waitFor(() =>
      expect(onImported).toHaveBeenCalledWith({
        gameId: "minted",
        platform: "dragncards",
      })
    );
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/proxy/history/import?as_new=true"
    );
  });

  it("imports under the bundle's own id when that target is chosen", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(importResult()));
    vi.stubGlobal("fetch", fetchMock);
    const onImported = vi.fn();

    render(
      <HistoryTransferControls
        gameId={null}
        onNotice={vi.fn()}
        onImported={onImported}
      />
    );
    pickBundle("bundle");

    await waitFor(() =>
      expect(onImported).toHaveBeenCalledWith({
        gameId: "g1",
        platform: "dragncards",
      })
    );
    // No target parameter at all: the bundle's header is what the service reads.
    expect(fetchMock.mock.calls[0][0]).toBe("/api/proxy/history/import");
  });

  it("imports under a typed id when that target is chosen", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonResponse(importResult({ game_id: "g1 copy", source_game_id: "g1" }))
      );
    vi.stubGlobal("fetch", fetchMock);
    const onImported = vi.fn();

    render(
      <HistoryTransferControls
        gameId={null}
        onNotice={vi.fn()}
        onImported={onImported}
      />
    );
    pickBundle("custom", "g1 copy");

    await waitFor(() =>
      expect(onImported).toHaveBeenCalledWith({
        gameId: "g1 copy",
        platform: "dragncards",
      })
    );
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/proxy/history/import?game_id=g1+copy"
    );
  });

  it("will not submit a typed target that is still blank", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(importResult()));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <HistoryTransferControls
        gameId={null}
        onNotice={vi.fn()}
        onImported={vi.fn()}
      />
    );
    fireEvent.change(screen.getByTestId("history-import-input"), {
      target: { files: [bundleFile()] },
    });
    fireEvent.click(await screen.findByTestId("history-import-target-custom"));
    fireEvent.click(screen.getByTestId("history-import-confirm"));

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reports what an accepted import wrote and selects the new game", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          jsonResponse(
            importResult({ game_id: "restored", source_game_id: "g1" })
          )
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
    pickBundle("new");

    await waitFor(() => {
      expect(onImported).toHaveBeenCalledWith({
        gameId: "restored",
        platform: "dragncards",
      });
    });
    expect(onNotice).toHaveBeenCalledWith({
      kind: "success",
      message:
        "Imported 12 events and 2 snapshots into restored (exported as g1) " +
        "from a full bundle.",
    });
  });

  it("selects the imported Marvel LCG partition", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          importResult({
            game_id: "shared",
            source_game_id: "g1",
            platform: "marvel-lcg",
          })
        )
      )
    );
    const onImported = vi.fn();

    render(
      <HistoryTransferControls
        gameId={null}
        onNotice={vi.fn()}
        onImported={onImported}
      />
    );
    pickBundle("new");

    await waitFor(() =>
      expect(onImported).toHaveBeenCalledWith({
        gameId: "shared",
        platform: "marvel-lcg",
      })
    );
  });

  it("says a minimal bundle carried no prompt material", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse(importResult({ mode: "minimal" })))
    );
    const onNotice = vi.fn();

    render(
      <HistoryTransferControls
        gameId={null}
        onNotice={onNotice}
        onImported={vi.fn()}
      />
    );
    pickBundle("bundle");

    await waitFor(() => {
      expect(onNotice).toHaveBeenCalledWith({
        kind: "success",
        message:
          "Imported 12 events and 2 snapshots into g1 from a minimal bundle, " +
          "which carries no agent prompt material.",
      });
    });
  });

  it("counts the imported events that still name the source game", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          importResult({
            game_id: "minted",
            source_game_id: "g1",
            source_id_references: 7,
          })
        )
      )
    );
    const onNotice = vi.fn();

    render(
      <HistoryTransferControls
        gameId={null}
        onNotice={onNotice}
        onImported={vi.fn()}
      />
    );
    pickBundle("new");

    await waitFor(() => {
      expect(onNotice).toHaveBeenCalledWith({
        kind: "success",
        message:
          "Imported 12 events and 2 snapshots into minted (exported as g1) " +
          "from a full bundle. 7 imported events still name g1 inside their " +
          "payloads.",
      });
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
    pickBundle("new");

    await waitFor(() => {
      expect(onNotice).toHaveBeenCalledWith({
        kind: "failure",
        message: "line 7: footer declares 9 events but 8 were read",
      });
    });
    expect(onImported).not.toHaveBeenCalled();
    // The dialog survives the failure so another target can be picked without
    // hunting down the file again.
    expect(screen.getByTestId("history-import-confirm")).toBeInTheDocument();
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
