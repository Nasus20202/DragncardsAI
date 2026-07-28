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
import { readLastUsedDraft } from "@/features/play/lib/last-used-draft";
import {
  buildDraftFromSession,
  createDefaultDraft,
  createNewSessionDraft,
  isWorking,
  withUsableProviderModel,
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
  setProvidersNotice: Dispatch<SetStateAction<string | null>>;
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
  setProvidersNotice,
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
    // The provider catalog is deliberately kept OFF the blocking initial-load
    // path. `/providers` probes the AI gateway, which can take several seconds
    // whenever a configured provider is unreachable; awaiting it here used to
    // leave the entire workspace on a bare spinner for that whole time.
    // Rejections are folded into `null` so this promise can never surface as an
    // unhandled rejection when the blocking load below bails out early.
    const providersPromise = listProviders().catch(() => null);

    function applyProviders(
      nextConfig: DashboardConfig,
      loadedProviders: ProviderResponse[] | null
    ) {
      // Surface a non-blocking notice when providers fail to load or report
      // themselves unavailable — never a fatal error.
      if (loadedProviders === null) {
        setProviders([]);
        setProvidersNotice(
          "Some providers could not be loaded. You can still use the providers that are available."
        );
        return;
      }

      setProviders(loadedProviders);

      // Re-point the selectors at a provider the user can actually use. This
      // runs only while no session has committed its own model, so a loaded
      // session that landed first always wins; before that the draft holds
      // either the configuration defaults or the restored last-used settings,
      // and both need validating against the catalog that just arrived.
      setDraft((current) => {
        if (!current || committedModelRef.current !== null) {
          return current;
        }
        return withUsableProviderModel(nextConfig, current, loadedProviders);
      });

      // A provider without an API key answers the model listing successfully but
      // with an empty list, so it reports `available: true` while being unusable.
      // Judge usability the same way the selectors do — `isWorking` — otherwise
      // the most common breakage produces no notice at all.
      const unusableProviders = loadedProviders
        .filter((provider) => !isWorking(provider))
        .map((provider) => provider.provider_id);
      setProvidersNotice(
        unusableProviders.length > 0
          ? `No models available from ${unusableProviders.join(", ")} — check their API keys in Bifrost. The remaining providers are unaffected.`
          : null
      );
    }

    async function load() {
      // Load the remaining initial data resiliently: a failure in any single
      // call must degrade gracefully rather than failing the whole dashboard.
      const [configResult, skillsResult, sessionsResult] =
        await Promise.allSettled([
          fetchDashboardConfig(),
          listAvailableSkills(),
          listSessions(),
        ]);

      // Dashboard config supplies the defaults needed to build a draft, so a
      // failure here is genuinely fatal.
      if (configResult.status === "rejected") {
        setErrorText(
          configResult.reason instanceof Error
            ? configResult.reason.message
            : "Failed to load dashboard configuration"
        );
        setStatusText("Configuration error");
        return;
      }
      const nextConfig = configResult.value;
      setConfig(nextConfig);

      if (skillsResult.status === "fulfilled") {
        setSkills(skillsResult.value);
      }

      const nextSessions =
        sessionsResult.status === "fulfilled" ? sessionsResult.value : [];
      setSessions(nextSessions);

      // Seed the draft so the workspace renders immediately, preferring the
      // settings the user last committed in this browser over the configuration
      // defaults; `applyProviders` refines the provider/model once the catalog
      // arrives, and selecting a session replaces the draft with that session's
      // own settings.
      const lastUsed = readLastUsedDraft();
      setDraft(
        lastUsed === null
          ? createDefaultDraft(nextConfig)
          : createNewSessionDraft(nextConfig, lastUsed)
      );

      // Apply the catalog whenever it lands — never before the rest of the UI.
      void providersPromise.then((loadedProviders) => {
        applyProviders(nextConfig, loadedProviders);
      });

      // Surface a visible error when sessions or skills fail to load, so a
      // rejected sessions fetch does not look identical to an empty account.
      // Providers degrade gracefully (notice only) and config stays the sole
      // fatal failure.
      const failedToLoad: string[] = [];
      if (sessionsResult.status === "rejected") {
        failedToLoad.push("sessions");
      }
      if (skillsResult.status === "rejected") {
        failedToLoad.push("skills");
      }
      if (failedToLoad.length > 0) {
        setErrorText(`Failed to load ${failedToLoad.join(" and ")}.`);
      } else {
        setErrorText(null);
      }

      setStatusText("Ready");
      if (nextSessions.length > 0 && typeof window !== "undefined") {
        const sessionIdFromUrl = readSelectedSessionIdFromUrl();
        const savedId = localStorage.getItem("play:selectedSessionId");
        const restoredId =
          sessionIdFromUrl &&
          nextSessions.some((session) => session.id === sessionIdFromUrl)
            ? sessionIdFromUrl
            : savedId && nextSessions.some((session) => session.id === savedId)
              ? savedId
              : nextSessions[0].id;
        persistSelectedSessionId(restoredId);
      }
    }

    void load();
  }, [
    committedModelRef,
    persistSelectedSessionId,
    setConfig,
    setDraft,
    setErrorText,
    setProviders,
    setProvidersNotice,
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
