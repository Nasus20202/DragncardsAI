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

describe("useBoardReconstruction session reuse (DRA-36)", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  /**
   * A history-service that honours `reuse_session_id`: it re-points the supplied
   * session and, having created no room, reports none.
   */
  function reusingFetch() {
    return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      if (url.includes("/restore")) {
        const body = JSON.parse((init?.body as string) ?? "{}");
        if (body.reuse_session_id) {
          return jsonResponse({
            status: "restored",
            session_id: body.reuse_session_id,
          });
        }
        return jsonResponse({
          status: "restored",
          session_id: "sess-first",
          room_slug: "room-first",
        });
      }
      return jsonResponse({});
    });
  }

  function restoreBodies(fetchMock: ReturnType<typeof vi.fn>) {
    return fetchMock.mock.calls
      .filter(([input]) => String(input).includes("/restore"))
      .map(([, init]) => JSON.parse((init as RequestInit).body as string));
  }

  function deletes(fetchMock: ReturnType<typeof vi.fn>) {
    return fetchMock.mock.calls
      .filter(
        ([, init]) => (init as RequestInit | undefined)?.method === "DELETE"
      )
      .map(([input]) => String(input));
  }

  it("re-points the session it already holds at the newly selected moment", async () => {
    const fetchMock = reusingFetch();
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(<Harness gameId="game-1" selectedSeq={5} />);
    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });
    await waitFor(() =>
      expect(screen.getByTestId("recon")).toHaveTextContent(
        "sess-first:room-first"
      )
    );

    // Move to another moment of the same game, then open again.
    await act(async () => {
      rerender(<Harness gameId="game-1" selectedSeq={9} />);
    });
    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });

    await waitFor(() =>
      expect(screen.getByTestId("recon")).toHaveTextContent(
        "sess-first:room-first"
      )
    );

    const bodies = restoreBodies(fetchMock);
    expect(bodies).toHaveLength(2);
    expect(bodies[0].reuse_session_id).toBeUndefined();
    // The saving being claimed: the second open re-points the open room rather
    // than building a second one.
    expect(bodies[1]).toMatchObject({
      target_seq: 9,
      mode: "new",
      ephemeral: true,
      reuse_session_id: "sess-first",
    });
    expect(deletes(fetchMock)).toHaveLength(0);
  });

  it("embeds the remembered room when a reuse reports no new room", async () => {
    const fetchMock = reusingFetch();
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(<Harness gameId="game-1" selectedSeq={5} />);
    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });
    await waitFor(() =>
      expect(screen.getByTestId("recon")).toBeInTheDocument()
    );
    await act(async () => {
      rerender(<Harness gameId="game-1" selectedSeq={9} />);
    });
    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });

    await waitFor(() =>
      expect(screen.getByTestId("recon")).toHaveTextContent(
        "sess-first:room-first"
      )
    );
    // A reuse creates no room, so it reports none — and the room is already
    // known. Listing every live session to rediscover it would be a wasted round
    // trip that also races the ephemeral reaper.
    const listed = fetchMock.mock.calls.filter(([input]) =>
      String(input).endsWith("/api/proxy/game/games")
    );
    expect(listed).toHaveLength(0);
  });

  it("stops showing the board when the moment changes but keeps the session", async () => {
    const fetchMock = reusingFetch();
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(<Harness gameId="game-1" selectedSeq={5} />);
    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });
    await waitFor(() =>
      expect(screen.getByTestId("recon")).toBeInTheDocument()
    );

    await act(async () => {
      rerender(<Harness gameId="game-1" selectedSeq={9} />);
    });

    // The header names the moment the board was built from, so the board has to
    // go; the session does not, because re-opening reuses it.
    expect(screen.queryByTestId("recon")).not.toBeInTheDocument();
    expect(deletes(fetchMock)).toHaveLength(0);
  });

  it("disposes the retained session when the game changes", async () => {
    const fetchMock = reusingFetch();
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(<Harness gameId="game-1" selectedSeq={5} />);
    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });
    await waitFor(() =>
      expect(screen.getByTestId("recon")).toBeInTheDocument()
    );

    // Hide the board first: the retained session survives that, so the game
    // switch is the only thing left that can reclaim it.
    await act(async () => {
      rerender(<Harness gameId="game-1" selectedSeq={9} />);
    });
    expect(deletes(fetchMock)).toHaveLength(0);

    await act(async () => {
      rerender(<Harness gameId="game-2" selectedSeq={9} />);
    });

    await waitFor(() =>
      expect(
        deletes(fetchMock).some((u) =>
          u.includes("/api/proxy/game/games/sess-first")
        )
      ).toBe(true)
    );
  });

  it("disposes the retained session when the service declines to reuse it", async () => {
    // A restore with no full-state base cannot safely reuse a session, so the
    // service builds a fresh one. The retained session is then orphaned.
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/restore")) {
          const body = JSON.parse((init?.body as string) ?? "{}");
          return jsonResponse({
            status: "restored",
            session_id: body.reuse_session_id ? "sess-second" : "sess-first",
            room_slug: body.reuse_session_id ? "room-second" : "room-first",
          });
        }
        return jsonResponse({});
      }
    );
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(<Harness gameId="game-1" selectedSeq={5} />);
    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });
    await waitFor(() =>
      expect(screen.getByTestId("recon")).toBeInTheDocument()
    );
    await act(async () => {
      rerender(<Harness gameId="game-1" selectedSeq={9} />);
    });
    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });

    await waitFor(() =>
      expect(screen.getByTestId("recon")).toHaveTextContent(
        "sess-second:room-second"
      )
    );
    await waitFor(() =>
      expect(
        deletes(fetchMock).some((u) =>
          u.includes("/api/proxy/game/games/sess-first")
        )
      ).toBe(true)
    );
  });

  it("keeps the retained session when a reuse restore fails", async () => {
    let attempts = 0;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === "string" ? input : input.toString();
        if (url.includes("/restore")) {
          attempts += 1;
          if (attempts === 1) {
            return jsonResponse({
              status: "restored",
              session_id: "sess-first",
              room_slug: "room-first",
            });
          }
          if (attempts === 2) {
            return {
              ok: false,
              status: 400,
              statusText: "Bad Request",
              json: async () => ({ detail: "replay diverged" }),
            } as unknown as Response;
          }
          const body = JSON.parse((init?.body as string) ?? "{}");
          return jsonResponse({
            status: "restored",
            session_id: body.reuse_session_id ?? "sess-other",
          });
        }
        return jsonResponse({});
      }
    );
    vi.stubGlobal("fetch", fetchMock);

    const { rerender } = render(<Harness gameId="game-1" selectedSeq={5} />);
    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });
    await waitFor(() =>
      expect(screen.getByTestId("recon")).toBeInTheDocument()
    );
    await act(async () => {
      rerender(<Harness gameId="game-1" selectedSeq={9} />);
    });
    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });
    await waitFor(() =>
      expect(screen.getByTestId("recon-error")).toBeInTheDocument()
    );

    // The history-service never deletes a session it did not create, so the
    // retained one is still ours — and the retry offers it again.
    expect(deletes(fetchMock)).toHaveLength(0);
    await act(async () => {
      fireEvent.click(screen.getByText("open"));
    });
    await waitFor(() =>
      expect(screen.getByTestId("recon")).toHaveTextContent(
        "sess-first:room-first"
      )
    );
    expect(restoreBodies(fetchMock)[2].reuse_session_id).toBe("sess-first");
  });
});
