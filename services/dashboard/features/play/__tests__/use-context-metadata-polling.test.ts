import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CONTEXT_METADATA_POLL_INTERVAL_MS,
  useContextMetadataPolling,
} from "@/features/play/lib/use-context-metadata-polling";

type PollProps = {
  sessionId: string | null;
  isActive: boolean;
  refreshContextMetadata: (sessionId: string) => Promise<void>;
};

describe("useContextMetadataPolling", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("refreshes immediately and polls again after each settled request", async () => {
    vi.useFakeTimers();
    const refreshContextMetadata = vi.fn().mockResolvedValue(undefined);

    renderHook(
      ({ sessionId, isActive, refreshContextMetadata }: PollProps) => {
        useContextMetadataPolling({
          sessionId,
          isActive,
          refreshContextMetadata,
        });
      },
      {
        initialProps: {
          sessionId: "session-1",
          isActive: true,
          refreshContextMetadata,
        },
      }
    );

    expect(refreshContextMetadata).toHaveBeenCalledTimes(1);
    expect(refreshContextMetadata).toHaveBeenLastCalledWith("session-1");

    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      vi.advanceTimersByTime(CONTEXT_METADATA_POLL_INTERVAL_MS);
      await Promise.resolve();
    });

    expect(refreshContextMetadata).toHaveBeenCalledTimes(2);
  });

  it("waits for a slow request instead of overlapping polls", async () => {
    vi.useFakeTimers();
    let resolveFirst: (() => void) | undefined;
    const firstRefresh = new Promise<void>((resolve) => {
      resolveFirst = resolve;
    });
    const refreshContextMetadata = vi
      .fn<(sessionId: string) => Promise<void>>()
      .mockReturnValueOnce(firstRefresh)
      .mockResolvedValue(undefined);

    renderHook(
      ({ sessionId, isActive, refreshContextMetadata }: PollProps) => {
        useContextMetadataPolling({
          sessionId,
          isActive,
          refreshContextMetadata,
        });
      },
      {
        initialProps: {
          sessionId: "session-1",
          isActive: true,
          refreshContextMetadata,
        },
      }
    );

    await act(async () => {
      vi.advanceTimersByTime(CONTEXT_METADATA_POLL_INTERVAL_MS * 3);
    });
    expect(refreshContextMetadata).toHaveBeenCalledTimes(1);

    await act(async () => {
      resolveFirst?.();
      await Promise.resolve();
    });
    await act(async () => {
      vi.advanceTimersByTime(CONTEXT_METADATA_POLL_INTERVAL_MS);
      await Promise.resolve();
    });

    expect(refreshContextMetadata).toHaveBeenCalledTimes(2);
  });

  it("stops polling when generation ends", async () => {
    vi.useFakeTimers();
    const refreshContextMetadata = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderHook(
      ({ sessionId, isActive, refreshContextMetadata }: PollProps) => {
        useContextMetadataPolling({
          sessionId,
          isActive,
          refreshContextMetadata,
        });
      },
      {
        initialProps: {
          sessionId: "session-1",
          isActive: true,
          refreshContextMetadata,
        },
      }
    );

    await act(async () => {
      await Promise.resolve();
    });
    rerender({
      sessionId: "session-1",
      isActive: false,
      refreshContextMetadata,
    });
    await act(async () => {
      vi.advanceTimersByTime(CONTEXT_METADATA_POLL_INTERVAL_MS * 2);
    });

    expect(refreshContextMetadata).toHaveBeenCalledTimes(1);
  });

  it("cleans up the old session timer when the session changes", async () => {
    vi.useFakeTimers();
    const refreshContextMetadata = vi.fn().mockResolvedValue(undefined);
    const { rerender, unmount } = renderHook(
      ({ sessionId, isActive, refreshContextMetadata }: PollProps) => {
        useContextMetadataPolling({
          sessionId,
          isActive,
          refreshContextMetadata,
        });
      },
      {
        initialProps: {
          sessionId: "session-1",
          isActive: true,
          refreshContextMetadata,
        },
      }
    );

    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    rerender({
      sessionId: "session-2",
      isActive: true,
      refreshContextMetadata,
    });
    expect(refreshContextMetadata).toHaveBeenLastCalledWith("session-2");

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => {
      vi.advanceTimersByTime(CONTEXT_METADATA_POLL_INTERVAL_MS);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(refreshContextMetadata).toHaveBeenCalledTimes(3);

    unmount();
    await act(async () => {
      vi.advanceTimersByTime(CONTEXT_METADATA_POLL_INTERVAL_MS * 2);
    });
    expect(refreshContextMetadata).toHaveBeenCalledTimes(3);
  });

  it("cleans up the timer when unmounted", async () => {
    vi.useFakeTimers();
    const refreshContextMetadata = vi.fn().mockResolvedValue(undefined);
    const { unmount } = renderHook(
      ({ sessionId, isActive, refreshContextMetadata }: PollProps) => {
        useContextMetadataPolling({
          sessionId,
          isActive,
          refreshContextMetadata,
        });
      },
      {
        initialProps: {
          sessionId: "session-1",
          isActive: true,
          refreshContextMetadata,
        },
      }
    );

    await act(async () => {
      await Promise.resolve();
    });
    unmount();
    await act(async () => {
      vi.advanceTimersByTime(CONTEXT_METADATA_POLL_INTERVAL_MS * 2);
    });

    expect(refreshContextMetadata).toHaveBeenCalledTimes(1);
  });
});
