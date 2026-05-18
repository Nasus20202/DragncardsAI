import {
  fetchDashboardConfig,
  getJob,
  getSession,
  listAvailableSkills,
  listSessionMcps,
  listProviders,
  listSessionJobs,
  listSessions,
} from "@/features/play/lib/client-api";
import {
  compareJobsOldestFirst,
  listUnresolvedSubagentJobIds,
} from "@/features/play/lib/play-session-events";
import {
  buildDraftFromSession,
  createDefaultDraft,
} from "@/features/play/lib/session-draft";
import { readSelectedSessionIdFromUrl } from "@/features/play/lib/workspace-state";
import {
  DashboardConfig,
  JobDetail,
  ProviderResponse,
  SessionDetail,
  SessionDraft,
  SessionSummary,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";
import {
  Dispatch,
  RefObject,
  SetStateAction,
  useCallback,
  useEffect,
} from "react";

interface UsePlaySessionLoaderOptions {
  config: DashboardConfig | null;
  selectedSessionId: string | null;
  persistSelectedSessionId: (id: string | null) => void;
  setConfig: Dispatch<SetStateAction<DashboardConfig | null>>;
  setProviders: Dispatch<SetStateAction<ProviderResponse[]>>;
  setSkills: Dispatch<SetStateAction<SkillDefinitionResponse[]>>;
  setSessions: Dispatch<SetStateAction<SessionSummary[]>>;
  setSelectedSession: Dispatch<SetStateAction<SessionDetail | null>>;
  setDraft: Dispatch<SetStateAction<SessionDraft | null>>;
  setJobs: Dispatch<SetStateAction<JobDetail[]>>;
  setChildJobStatuses: Dispatch<SetStateAction<Map<string, string>>>;
  setStatusText: Dispatch<SetStateAction<string>>;
  setErrorText: Dispatch<SetStateAction<string | null>>;
  committedModelRef: RefObject<{
    providerId: string;
    modelName: string;
  } | null>;
  refreshContextMetadata: (sessionId: string) => Promise<void>;
  startStreaming: (jobId: string, afterId: string) => void;
  stopStreaming: () => void;
}

export function usePlaySessionLoader({
  config,
  selectedSessionId,
  persistSelectedSessionId,
  setConfig,
  setProviders,
  setSkills,
  setSessions,
  setSelectedSession,
  setDraft,
  setJobs,
  setChildJobStatuses,
  setStatusText,
  setErrorText,
  committedModelRef,
  refreshContextMetadata,
  startStreaming,
  stopStreaming,
}: UsePlaySessionLoaderOptions) {
  const loadAllJobs = useCallback(
    async (sessionId: string): Promise<JobDetail[]> => {
      const summary = await listSessionJobs(sessionId);
      const detailed = await Promise.all(
        summary.jobs.map((item) => getJob(item.id))
      );
      const sorted = [...detailed].sort(compareJobsOldestFirst);
      setJobs(sorted);

      const unresolvedSubagentJobIds = listUnresolvedSubagentJobIds(sorted);
      if (unresolvedSubagentJobIds.length > 0) {
        const fetched = await Promise.allSettled(
          unresolvedSubagentJobIds.map((id) => getJob(id))
        );
        const statusMap = new Map<string, string>();
        for (
          let index = 0;
          index < unresolvedSubagentJobIds.length;
          index += 1
        ) {
          const result = fetched[index];
          if (result.status === "fulfilled") {
            statusMap.set(unresolvedSubagentJobIds[index], result.value.status);
          }
        }
        setChildJobStatuses(statusMap);
      } else {
        setChildJobStatuses(new Map());
      }

      return sorted;
    },
    [setChildJobStatuses, setJobs]
  );

  useEffect(() => {
    async function load() {
      try {
        const [nextConfig, nextProviders, nextSkills, nextSessions] =
          await Promise.all([
            fetchDashboardConfig(),
            listProviders(),
            listAvailableSkills(),
            listSessions(),
          ]);
        setConfig(nextConfig);
        setProviders(nextProviders);
        setSkills(nextSkills);
        setSessions(nextSessions);
        setDraft(createDefaultDraft(nextConfig));
        setStatusText("Ready");
        if (nextSessions.length > 0 && typeof window !== "undefined") {
          const sessionIdFromUrl = readSelectedSessionIdFromUrl();
          const savedId = localStorage.getItem("play:selectedSessionId");
          const restoredId =
            sessionIdFromUrl &&
            nextSessions.some((session) => session.id === sessionIdFromUrl)
              ? sessionIdFromUrl
              : savedId &&
                  nextSessions.some((session) => session.id === savedId)
                ? savedId
                : nextSessions[0].id;
          persistSelectedSessionId(restoredId);
        }
      } catch (error) {
        setErrorText(
          error instanceof Error ? error.message : "Failed to load dashboard"
        );
        setStatusText("Configuration error");
      }
    }

    void load();
  }, [
    persistSelectedSessionId,
    setConfig,
    setDraft,
    setErrorText,
    setProviders,
    setSessions,
    setSkills,
    setStatusText,
  ]);

  useEffect(() => {
    if (!selectedSessionId || !config) {
      return;
    }

    const currentSessionId = selectedSessionId;
    const currentConfig = config;

    async function loadSession() {
      try {
        setStatusText("Loading session...");
        const [nextSession, nextMcps] = await Promise.all([
          getSession(currentSessionId),
          listSessionMcps(currentSessionId),
        ]);
        const hydratedSession = { ...nextSession, mcps: nextMcps };
        setSelectedSession(hydratedSession);
        const nextDraft = buildDraftFromSession(currentConfig, hydratedSession);
        setDraft(nextDraft);
        committedModelRef.current = {
          providerId: nextDraft.providerId,
          modelName: nextDraft.modelName,
        };

        const allJobs = await loadAllJobs(currentSessionId);
        void refreshContextMetadata(currentSessionId);

        const newestJob = allJobs.at(-1);
        if (newestJob && ["queued", "running"].includes(newestJob.status)) {
          startStreaming(newestJob.id, "0");
        } else {
          stopStreaming();
        }

        setStatusText("Ready");
        setErrorText(null);
      } catch (error) {
        setErrorText(
          error instanceof Error ? error.message : "Failed to load session"
        );
        setStatusText("Session load failed");
      }
    }

    void loadSession();

    return () => {
      stopStreaming();
    };
  }, [
    committedModelRef,
    config,
    loadAllJobs,
    refreshContextMetadata,
    selectedSessionId,
    setDraft,
    setErrorText,
    setSelectedSession,
    setStatusText,
    startStreaming,
    stopStreaming,
  ]);

  return {
    loadAllJobs,
  };
}
