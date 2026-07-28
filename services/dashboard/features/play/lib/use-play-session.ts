import {
  addMcp,
  addMcpRegistry,
  addSkill,
  enableMcpForSession,
  getSession,
  getContextMetadata,
  listSessionMcps,
  listSessions,
  removeMcp,
  removeMcpRegistry,
  removeSkill,
  setModelConfig,
} from "@/features/play/lib/client-api";
import { writeLastUsedDraft } from "@/features/play/lib/last-used-draft";
import {
  deriveSubagentEntries,
  SubagentEntry,
} from "@/features/play/lib/play-session-events";
import { usePlaySessionActions } from "@/features/play/lib/use-play-session-actions";
import { useJobStreaming } from "@/features/play/lib/use-job-streaming";
import { usePlaySessionLoader } from "@/features/play/lib/use-play-session-loader";
import {
  dedupeProviders,
  writeSelectedSessionIdToUrl,
} from "@/features/play/lib/workspace-state";
import {
  ContextMetadata,
  DashboardConfig,
  JobDetail,
  JsonValue,
  McpRegistryResponse,
  ProviderResponse,
  SessionDetail,
  SessionDraft,
  SessionSummary,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";
import {
  Dispatch,
  SetStateAction,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

interface UsePlaySessionResult {
  config: DashboardConfig | null;
  draft: SessionDraft | null;
  providers: ProviderResponse[];
  uniqueProviders: ProviderResponse[];
  modelOptions: string[];
  skills: SkillDefinitionResponse[];
  sessions: SessionSummary[];
  selectedSessionId: string | null;
  selectedSession: SessionDetail | null;
  jobs: JobDetail[];
  prompt: string;
  statusText: string;
  errorText: string | null;
  providersNotice: string | null;
  isBusy: boolean;
  cancelPending: boolean;
  contextMetadata: ContextMetadata | null;
  subagentEntries: SubagentEntry[];
  subagentChildSessionIds: Set<string>;
  streamingJobId: string | null;
  streamState: "idle" | "streaming";
  setDraft: Dispatch<SetStateAction<SessionDraft | null>>;
  setPrompt: Dispatch<SetStateAction<string>>;
  selectSession: (id: string | null) => void;
  createPlaySession: () => Promise<void>;
  saveConfiguration: () => Promise<void>;
  terminatePlaySession: () => Promise<void>;
  removeSession: (sessionId: string) => Promise<void>;
  compactPlaySession: () => Promise<void>;
  submitSessionPrompt: () => Promise<void>;
  cancelExecution: () => Promise<void>;
  recordSubagentOutcome: (
    childJobId: string,
    outcome: "completed" | "failed"
  ) => void;
  toggleSkill: (skillName: string, enabled: boolean) => Promise<void>;
  toggleMcp: (mcpName: string, enabled: boolean) => Promise<void>;
  addMcpToRegistry: (mcp: McpRegistryResponse) => Promise<void>;
  deleteMcpFromRegistry: (mcpName: string) => Promise<void>;
}

function normalizeDraft(
  nextDraft: SessionDraft | null,
  providers: ProviderResponse[]
): SessionDraft | null {
  if (!nextDraft) {
    return nextDraft;
  }

  const selectedProvider = providers.find(
    (provider) => provider.provider_id === nextDraft.providerId
  );
  if (!selectedProvider) {
    return nextDraft;
  }

  const allowedModels = [...new Set(selectedProvider.models)].sort(
    (left, right) => left.localeCompare(right)
  );
  if (
    allowedModels.length === 0 ||
    allowedModels.includes(nextDraft.modelName)
  ) {
    return nextDraft;
  }

  return { ...nextDraft, modelName: allowedModels[0] };
}

export function usePlaySession(): UsePlaySessionResult {
  const [config, setConfig] = useState<DashboardConfig | null>(null);
  const [providers, setProviders] = useState<ProviderResponse[]>([]);
  const [skills, setSkills] = useState<SkillDefinitionResponse[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(
    null
  );
  const [selectedSession, setSelectedSession] = useState<SessionDetail | null>(
    null
  );
  const [draft, setDraftState] = useState<SessionDraft | null>(null);
  const [jobs, setJobs] = useState<JobDetail[]>([]);
  const [childJobStatuses, setChildJobStatuses] = useState<Map<string, string>>(
    new Map()
  );
  const [prompt, setPrompt] = useState("");
  const [statusText, setStatusText] = useState("Loading dashboard...");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [providersNotice, setProvidersNotice] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [isCancellingExecution, setIsCancellingExecution] = useState(false);
  const [contextMetadata, setContextMetadata] =
    useState<ContextMetadata | null>(null);
  const committedModelRef = useRef<{
    providerId: string;
    modelName: string;
  } | null>(null);

  const uniqueProviders = useMemo(
    () => dedupeProviders(providers),
    [providers]
  );
  const uniqueProvidersRef = useRef<ProviderResponse[]>(uniqueProviders);
  useEffect(() => {
    uniqueProvidersRef.current = uniqueProviders;
  }, [uniqueProviders]);
  const selectedProvider = useMemo(
    () =>
      uniqueProviders.find(
        (provider) => provider.provider_id === draft?.providerId
      ) ?? null,
    [draft?.providerId, uniqueProviders]
  );
  const modelOptions = useMemo(() => {
    const models = selectedProvider?.models ?? [];
    return [...new Set(models)].sort((left, right) =>
      left.localeCompare(right)
    );
  }, [selectedProvider]);
  const setDraft = useCallback<Dispatch<SetStateAction<SessionDraft | null>>>(
    (value) => {
      setDraftState((current) => {
        const nextDraft =
          typeof value === "function"
            ? (
                value as (prevState: SessionDraft | null) => SessionDraft | null
              )(current)
            : value;
        return normalizeDraft(nextDraft, uniqueProvidersRef.current);
      });
    },
    []
  );

  const persistSelectedSessionId = useCallback((id: string | null) => {
    setSelectedSessionId(id);
    writeSelectedSessionIdToUrl(id);
    if (typeof window === "undefined") {
      return;
    }
    if (id) {
      localStorage.setItem("play:selectedSessionId", id);
    } else {
      localStorage.removeItem("play:selectedSessionId");
    }
  }, []);

  const refreshContextMetadata = useCallback(async (sessionId: string) => {
    try {
      const metadata = await getContextMetadata(sessionId);
      setContextMetadata(metadata);
    } catch {
      // Non-fatal: ignore metadata fetch errors
    }
  }, []);

  const refreshSessions = useCallback(
    async (preserveSelected = true): Promise<SessionSummary[]> => {
      const nextSessions = await listSessions();
      setSessions(nextSessions);
      if (!preserveSelected && nextSessions.length > 0) {
        persistSelectedSessionId(nextSessions[0].id);
      }
      return nextSessions;
    },
    [persistSelectedSessionId]
  );

  const refreshCurrentSessions = useCallback(async () => {
    await refreshSessions();
  }, [refreshSessions]);

  const refreshSelectedSession = useCallback(
    async (sessionId: string) => {
      const [session, mcps] = await Promise.all([
        getSession(sessionId),
        listSessionMcps(sessionId),
      ]);
      const hydratedSession = { ...session, mcps };
      setSelectedSession(hydratedSession);
      return hydratedSession;
    },
    [setSelectedSession]
  );

  const { startStreaming, stopStreaming, streamingJobId, streamState } =
    useJobStreaming({
      selectedSessionId,
      setJobs,
      refreshContextMetadata,
      refreshSessions: refreshCurrentSessions,
    });

  const streamingJob = useMemo(
    () => jobs.find((job) => job.id === streamingJobId) ?? null,
    [jobs, streamingJobId]
  );
  const cancelPending =
    isCancellingExecution || Boolean(streamingJob?.cancellation_requested_at);
  const subagentEntries = useMemo(
    () => deriveSubagentEntries(jobs, childJobStatuses),
    [jobs, childJobStatuses]
  );
  // Session ids belonging to subagent children; the sidebar hides these, so
  // removeSession must use the same set when reselecting after a removal.
  const subagentChildSessionIds = useMemo(
    () => new Set(subagentEntries.map((entry) => entry.childSessionId)),
    [subagentEntries]
  );

  const { loadAllJobs } = usePlaySessionLoader({
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
  });

  useEffect(() => {
    if (!draft || !selectedSession) {
      return;
    }
    const committed = committedModelRef.current;
    if (
      committed &&
      committed.providerId === draft.providerId &&
      committed.modelName === draft.modelName
    ) {
      return;
    }
    committedModelRef.current = {
      providerId: draft.providerId,
      modelName: draft.modelName,
    };
    // Picking a provider/model in the panel commits it to the session straight
    // away, so it is also the configuration a later new session should inherit.
    writeLastUsedDraft(draft);
    void setModelConfig(selectedSession.id, {
      provider_id: draft.providerId,
      model_name: draft.modelName,
      gateway_options:
        (selectedSession.model_config?.gateway_options as Record<
          string,
          JsonValue
        >) ?? {},
      provider_options:
        (selectedSession.model_config?.provider_options as Record<
          string,
          JsonValue
        >) ?? {},
    });
  }, [draft, selectedSession]);

  const {
    createPlaySession,
    saveConfiguration,
    terminatePlaySession,
    removeSession,
    compactPlaySession,
    submitSessionPrompt,
    cancelExecution,
  } = usePlaySessionActions({
    config,
    draft,
    providers,
    subagentChildSessionIds,
    selectedSession,
    selectedSessionId,
    jobsCount: jobs.length,
    prompt,
    streamingJobId,
    cancelPending,
    refreshSessions,
    persistSelectedSessionId,
    loadAllJobs,
    refreshContextMetadata,
    startStreaming,
    setSelectedSession,
    setDraft,
    setJobs,
    setPrompt,
    setStatusText,
    setErrorText,
    setIsBusy,
    setIsCancellingExecution,
    setContextMetadata,
    committedModelRef,
  });

  const recordSubagentOutcome = useCallback(
    (childJobId: string, outcome: "completed" | "failed") => {
      setChildJobStatuses((current) => {
        const next = new Map(current);
        next.set(childJobId, outcome);
        return next;
      });
    },
    []
  );

  /**
   * Assign or unassign one skill for the selected session, right away.
   *
   * This is the composer's `@`-mention path, and it drives the *same* session
   * skill assignment the settings panel's toggle list drives: the persisted call
   * is the one `saveConfiguration` replays, and the draft's `selectedSkills` —
   * which the settings toggles read — is updated in step, so a skill attached
   * from chat shows as enabled in the panel and vice versa. Applying it
   * immediately rather than on Save mirrors how MCP assignment already behaves.
   *
   * Only the named skill's membership changes, so unsaved edits the user has made
   * to other skills in the settings panel survive.
   */
  const toggleSkill = useCallback(
    async (skillName: string, enabled: boolean) => {
      if (!selectedSession) {
        return;
      }
      setIsBusy(true);
      setStatusText(enabled ? "Attaching skill..." : "Detaching skill...");
      try {
        if (enabled) {
          await addSkill(selectedSession.id, skillName);
        } else {
          await removeSkill(selectedSession.id, skillName);
        }
        setDraft((current) =>
          current
            ? {
                ...current,
                selectedSkills: enabled
                  ? current.selectedSkills.includes(skillName)
                    ? current.selectedSkills
                    : [...current.selectedSkills, skillName]
                  : current.selectedSkills.filter((name) => name !== skillName),
              }
            : current
        );
        await refreshSelectedSession(selectedSession.id);
        setStatusText(enabled ? "Skill attached" : "Skill detached");
      } catch (error) {
        setErrorText(
          error instanceof Error ? error.message : "Failed to update skill"
        );
        setStatusText("Skill update failed");
      } finally {
        setIsBusy(false);
      }
    },
    [
      refreshSelectedSession,
      selectedSession,
      setDraft,
      setErrorText,
      setIsBusy,
      setStatusText,
    ]
  );

  const toggleMcp = useCallback(
    async (mcpName: string, enabled: boolean) => {
      if (!selectedSession) {
        return;
      }
      setIsBusy(true);
      setStatusText(enabled ? "Enabling MCP..." : "Disabling MCP...");
      try {
        await enableMcpForSession(selectedSession.id, mcpName, enabled);
        await refreshSessions();
        await refreshSelectedSession(selectedSession.id);
        setStatusText("MCP updated");
      } catch (error) {
        setErrorText(
          error instanceof Error ? error.message : "Failed to update MCP"
        );
        setStatusText("MCP update failed");
      } finally {
        setIsBusy(false);
      }
    },
    [
      selectedSession,
      refreshSessions,
      refreshSelectedSession,
      setStatusText,
      setErrorText,
      setIsBusy,
    ]
  );

  const addMcpToRegistry = useCallback(
    async (mcp: McpRegistryResponse) => {
      if (!selectedSession) {
        return;
      }
      setIsBusy(true);
      setStatusText("Creating MCP...");
      try {
        await addMcpRegistry(mcp);
        if (!mcp.custom) {
          await addMcp(selectedSession.id, {
            name: mcp.name,
            transport: mcp.transport,
            server_url: mcp.server_url,
            headers: mcp.headers as Record<string, string>,
          });
        }
        await refreshSessions();
        await refreshSelectedSession(selectedSession.id);
        setStatusText(mcp.custom ? "MCP created" : "MCP added");
      } catch (error) {
        setErrorText(
          error instanceof Error ? error.message : "Failed to create MCP"
        );
        setStatusText("MCP create failed");
      } finally {
        setIsBusy(false);
      }
    },
    [
      refreshSessions,
      refreshSelectedSession,
      selectedSession,
      setStatusText,
      setErrorText,
      setIsBusy,
    ]
  );

  const deleteMcpFromRegistry = useCallback(
    async (mcpName: string) => {
      if (!selectedSession) {
        return;
      }
      setIsBusy(true);
      setStatusText("Deleting MCP...");
      try {
        const target = selectedSession.mcps.find((mcp) => mcp.name === mcpName);
        if (target?.enabled) {
          await removeMcp(selectedSession.id, mcpName);
        }
        await removeMcpRegistry(mcpName);
        await refreshSessions();
        await refreshSelectedSession(selectedSession.id);
        setStatusText("MCP deleted");
      } catch (error) {
        setErrorText(
          error instanceof Error ? error.message : "Failed to delete MCP"
        );
        setStatusText("MCP delete failed");
      } finally {
        setIsBusy(false);
      }
    },
    [
      refreshSessions,
      refreshSelectedSession,
      selectedSession,
      setErrorText,
      setIsBusy,
      setStatusText,
    ]
  );

  return {
    config,
    draft,
    providers,
    uniqueProviders,
    modelOptions,
    skills,
    sessions,
    selectedSessionId,
    selectedSession,
    jobs,
    prompt,
    statusText,
    errorText,
    providersNotice,
    isBusy,
    cancelPending,
    contextMetadata,
    subagentEntries,
    subagentChildSessionIds,
    streamingJobId,
    streamState,
    setDraft,
    setPrompt,
    selectSession: persistSelectedSessionId,
    createPlaySession,
    saveConfiguration,
    terminatePlaySession,
    removeSession,
    compactPlaySession,
    submitSessionPrompt,
    cancelExecution,
    recordSubagentOutcome,
    toggleSkill,
    toggleMcp,
    addMcpToRegistry,
    deleteMcpFromRegistry,
  };
}
