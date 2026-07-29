import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import "@testing-library/jest-dom";

import { useBoardReconstruction } from "@/features/history/lib/use-board-reconstruction";

/**
 * A thin harness that drives the reconstruction hook and surfaces its state +
 * actions as DOM, so we can assert the open → restore → resolve → embed flow
 * and teardown on unmount/close.
 */
function Harness({
  gameId,
  selectedSeq,
}: {
  gameId: string | null;
  selectedSeq: number | null;
}) {
  const board = useBoardReconstruction(gameId, selectedSeq);
  return (
    <div>
      <button type="button" onClick={() => void board.open()}>
        open
      </button>
      <button type="button" onClick={board.close}>
        close
      </button>
      {board.reconstruction && (
        <span data-testid="recon">
          {board.reconstruction.sessionId}:{board.reconstruction.roomSlug}
        </span>
      )}
      {board.error && <span data-testid="recon-error">{board.error}</span>}
    </div>
  );
}

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => body,
  } as unknown as Response;
}

describe("useBoardReconstruction", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      const method = init?.method ?? "GET";

      if (url.includes("/restore")) {
        return jsonResponse({ status: "ok", session_id: "sess-new" });
      }
      if (url.endsWith("/api/proxy/game/games")) {
        return jsonResponse({
          sessions: [
            {
              session_id: "sess-new",
              plugin_name: "marvel",
              plugin_id: 1,
              room_slug: "room-xyz",
              created_at: "2026-06-24T00:00:00Z",
            },
          ],
        });
      }
      if (method === "DELETE" && url.includes("/api/proxy/game/games/")) {
        return jsonResponse({ ok: true });
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function deleteCalls(): string[] {
    return fetchMock.mock.calls
      .filter(
        ([, init]) => (init as RequestInit | undefined)?.method === "DELETE"
      )
      .map(([input]) => (typeof input === "string" ? input : String(input)));
  }

  it("open restores an ephemeral session, resolves room_slug, and embeds it", async () => {
    render(<Harness gameId="game-1" selectedSeq={5} />);

    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });

    await waitFor(() =>
      expect(screen.getByTestId("recon")).toHaveTextContent("sess-new:room-xyz")
    );

    // Restore was called with mode "new" + ephemeral true.
    const restoreCall = fetchMock.mock.calls.find(([input]) =>
      String(input).includes("/restore")
    );
    expect(restoreCall).toBeDefined();
    const body = JSON.parse((restoreCall![1] as RequestInit).body as string);
    expect(body).toMatchObject({
      target_seq: 5,
      mode: "new",
      ephemeral: true,
    });
  });

  it("deletes the game-service session on unmount (no history delete)", async () => {
    const { unmount } = render(<Harness gameId="game-1" selectedSeq={5} />);

    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });
    await waitFor(() =>
      expect(screen.getByTestId("recon")).toBeInTheDocument()
    );

    await act(async () => {
      unmount();
    });

    await waitFor(() => {
      const deletes = deleteCalls();
      expect(
        deletes.some((u) => u.includes("/api/proxy/game/games/sess-new"))
      ).toBe(true);
    });

    // Teardown must NOT delete history for the ephemeral (non-emitting) session.
    expect(
      deleteCalls().some((u) => u.includes("/api/proxy/history/games/"))
    ).toBe(false);
  });

  it("deletes the session on explicit close", async () => {
    render(<Harness gameId="game-1" selectedSeq={5} />);

    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });
    await waitFor(() =>
      expect(screen.getByTestId("recon")).toBeInTheDocument()
    );

    await act(async () => {
      fireEvent.click(screen.getByText("close"));
    });

    await waitFor(() =>
      expect(screen.queryByTestId("recon")).not.toBeInTheDocument()
    );
    expect(
      deleteCalls().some((u) => u.includes("/api/proxy/game/games/sess-new"))
    ).toBe(true);
  });

  it("disposes the session via keepalive fetch on pagehide", async () => {
    render(<Harness gameId="game-1" selectedSeq={5} />);

    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });
    await waitFor(() =>
      expect(screen.getByTestId("recon")).toBeInTheDocument()
    );

    await act(async () => {
      window.dispatchEvent(new Event("pagehide"));
    });

    const keepaliveDelete = fetchMock.mock.calls.find(
      ([input, init]) =>
        (init as RequestInit | undefined)?.method === "DELETE" &&
        (init as RequestInit | undefined)?.keepalive === true &&
        String(input).includes("/api/proxy/game/games/sess-new")
    );
    expect(keepaliveDelete).toBeDefined();
  });

  it("keeps the reconstruction alive while the tab is merely hidden", async () => {
    render(<Harness gameId="game-1" selectedSeq={5} />);

    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });
    await waitFor(() =>
      expect(screen.getByTestId("recon")).toBeInTheDocument()
    );

    // Switching browser tabs / minimizing hides the document. That is not the
    // end of the view: disposing here would delete the session out from under a
    // board the user is still looking at (leaving its room orphaned and the UI
    // claiming a reconstruction that no longer exists).
    const visibility = vi
      .spyOn(document, "visibilityState", "get")
      .mockReturnValue("hidden");
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    visibility.mockRestore();

    expect(screen.getByTestId("recon")).toBeInTheDocument();
    expect(deleteCalls()).toHaveLength(0);

    // The board is still live, so an explicit close still tears it down.
    await act(async () => {
      fireEvent.click(screen.getByText("close"));
    });
    await waitFor(() =>
      expect(
        deleteCalls().some((u) => u.includes("/api/proxy/game/games/sess-new"))
      ).toBe(true)
    );
  });

  it("surfaces an error when restore returns no session id", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      if (String(input).includes("/restore")) {
        return jsonResponse({ status: "ok" });
      }
      return jsonResponse({});
    });

    render(<Harness gameId="game-1" selectedSeq={5} />);
    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });

    await waitFor(() =>
      expect(screen.getByTestId("recon-error")).toBeInTheDocument()
    );
    expect(screen.queryByTestId("recon")).not.toBeInTheDocument();
  });
});

describe("useBoardReconstruction room resolution (DRA-28)", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("uses the room_slug the restore returned instead of listing every session", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/restore")) {
        return jsonResponse({
          status: "restored",
          session_id: "sess-new",
          room_slug: "room-from-restore",
        });
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Harness gameId="game-1" selectedSeq={5} />);
    fireEvent.click(screen.getByText("open"));

    await waitFor(() => {
      expect(screen.getByTestId("recon")).toHaveTextContent(
        "sess-new:room-from-restore"
      );
    });
    // The session list is a fallback for an older service, not the normal path:
    // it costs a round trip after the restore already finished and races the
    // ephemeral reaper.
    const listed = fetchMock.mock.calls.filter(([input]) =>
      String(input).endsWith("/api/proxy/game/games")
    );
    expect(listed).toHaveLength(0);
  });

  it("falls back to the session list when the restore names no room", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/restore")) {
        return jsonResponse({ status: "restored", session_id: "sess-new" });
      }
      if (url.endsWith("/api/proxy/game/games")) {
        return jsonResponse({
          sessions: [
            {
              session_id: "sess-new",
              plugin_name: "marvel",
              plugin_id: 1,
              room_slug: "room-xyz",
              created_at: "2026-06-24T00:00:00Z",
            },
          ],
        });
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Harness gameId="game-1" selectedSeq={5} />);
    fireEvent.click(screen.getByText("open"));

    await waitFor(() => {
      expect(screen.getByTestId("recon")).toHaveTextContent(
        "sess-new:room-xyz"
      );
    });
  });
});
