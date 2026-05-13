import { getJob } from "@/features/play/lib/client-api";
import {
  applyStreamEventToJob,
  mergeJob,
  STREAM_EVENT_TYPES,
  SUBAGENT_TERMINAL_EVENT_TYPES,
  TERMINAL_EVENT_TYPES,
} from "@/features/play/lib/play-session-events";
import { JobDetail, JobEventResponse } from "@/features/shared/lib/types";
import { Dispatch, SetStateAction, useCallback, useRef, useState } from "react";

interface UseJobStreamingOptions {
  selectedSessionId: string | null;
  setJobs: Dispatch<SetStateAction<JobDetail[]>>;
  refreshContextMetadata: (sessionId: string) => Promise<void>;
  refreshSessions: () => Promise<void>;
}

export function useJobStreaming({
  selectedSessionId,
  setJobs,
  refreshContextMetadata,
  refreshSessions,
}: UseJobStreamingOptions) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const streamingJobIdRef = useRef<string | null>(null);
  const [streamingJobId, setStreamingJobId] = useState<string | null>(null);
  const [streamState, setStreamState] = useState<"idle" | "streaming">("idle");

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimeoutRef.current !== null) {
      window.clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
  }, []);

  const closeEventSource = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    clearReconnectTimer();
  }, [clearReconnectTimer]);

  const stopStreaming = useCallback(() => {
    closeEventSource();
    streamingJobIdRef.current = null;
    setStreamingJobId(null);
    setStreamState("idle");
  }, [closeEventSource]);

  const appendStreamEvent = useCallback(
    (payload: JobEventResponse) => {
      const jobId = streamingJobIdRef.current;
      if (!jobId) {
        return;
      }

      setJobs((current) => {
        const index = current.findIndex((job) => job.id === jobId);
        if (index < 0) {
          return current;
        }

        const updatedJob = applyStreamEventToJob(current[index], payload);
        if (!updatedJob) {
          return current;
        }

        const next = [...current];
        next[index] = updatedJob;
        return next;
      });
    },
    [setJobs]
  );

  const startStreaming = useCallback(
    (jobId: string, afterId: string) => {
      const connect = (currentAfterId: string) => {
        closeEventSource();
        streamingJobIdRef.current = jobId;
        setStreamingJobId(jobId);
        const source = new EventSource(
          `/api/proxy/orchestrator/jobs/${jobId}/events/stream?after=${currentAfterId}`
        );
        eventSourceRef.current = source;
        setStreamState("streaming");

        let pendingSubagents = 0;
        let parentTerminated = false;

        const finishStreaming = () => {
          stopStreaming();
          if (selectedSessionId) {
            void refreshContextMetadata(selectedSessionId);
          }
          void refreshSessions();
        };

        const maybeStop = () => {
          if (!parentTerminated || pendingSubagents > 0) {
            return;
          }
          finishStreaming();
        };

        const handleEvent = (event: MessageEvent<string>) => {
          const payload = JSON.parse(event.data) as JobEventResponse;
          appendStreamEvent(payload);
          if (payload.event_type === "compaction" && selectedSessionId) {
            void refreshContextMetadata(selectedSessionId);
          }
          if (payload.event_type === "subagent_started") {
            pendingSubagents += 1;
          }
          if (SUBAGENT_TERMINAL_EVENT_TYPES.has(payload.event_type)) {
            pendingSubagents = Math.max(0, pendingSubagents - 1);
            maybeStop();
          }
          if (TERMINAL_EVENT_TYPES.has(payload.event_type)) {
            parentTerminated = true;
            maybeStop();
          }
        };

        for (const eventType of STREAM_EVENT_TYPES) {
          source.addEventListener(eventType, handleEvent as EventListener);
        }
        source.onmessage = handleEvent;
        source.onerror = () => {
          source.close();
          if (eventSourceRef.current === source) {
            eventSourceRef.current = null;
          }
          clearReconnectTimer();
          reconnectTimeoutRef.current = window.setTimeout(async () => {
            if (streamingJobIdRef.current !== jobId) {
              return;
            }
            try {
              const refreshedJob = await getJob(jobId);
              setJobs((current) => mergeJob(current, refreshedJob));
              if (streamingJobIdRef.current !== jobId) {
                return;
              }
              if (["queued", "running"].includes(refreshedJob.status)) {
                // Reconnect from 0 so subagent_started/completed events are all
                // replayed and pendingSubagents is correctly re-counted.
                connect("0");
              } else {
                finishStreaming();
              }
            } catch {
              if (streamingJobIdRef.current === jobId) {
                connect("0");
              }
            }
          }, 1000);
        };
      };

      connect(afterId);
    },
    [
      appendStreamEvent,
      clearReconnectTimer,
      closeEventSource,
      refreshContextMetadata,
      refreshSessions,
      selectedSessionId,
      setJobs,
      stopStreaming,
    ]
  );

  return {
    startStreaming,
    stopStreaming,
    streamingJobId,
    streamState,
  };
}
