import {
  getContextMetadata,
  listSessions,
  setModelConfig,
} from "@/features/play/lib/client-api";
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
  isBusy: boolean;
  cancelPending: boolean;
  contextMetadata: ContextMetadata | null;
  subagentEntries: SubagentEntry[];
  streamingJobId: string | null;
  streamState: "idle" | "streaming";
  setDraft: Dispatch<SetStateAction<SessionDraft | null>>;
  setPrompt: Dispatch<SetStateAction<string>>;
  selectSession: (id: string | null) => void;
  createPlaySession: () => Promise<void>;
  saveConfiguration: () => Promise<void>;
  terminatePlaySession: () => Promise<void>;
  compactPlaySession: () => Promise<void>;
  submitSessionPrompt: () => Promise<void>;
  cancelExecution: () => Promise<void>;
  recordSubagentOutcome: (
    childJobId: string,
    outcome: "completed" | "failed"
  ) => void;
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
    async (preserveSelected = true) => {
      const nextSessions = await listSessions();
      setSessions(nextSessions);
      if (!preserveSelected && nextSessions.length > 0) {
        persistSelectedSessionId(nextSessions[0].id);
      }
    },
    [persistSelectedSessionId]
  );

  const refreshCurrentSessions = useCallback(async () => {
    await refreshSessions();
  }, [refreshSessions]);

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
    compactPlaySession,
    submitSessionPrompt,
    cancelExecution,
  } = usePlaySessionActions({
    config,
    draft,
    selectedSession,
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
    isBusy,
    cancelPending,
    contextMetadata,
    subagentEntries,
    streamingJobId,
    streamState,
    setDraft,
    setPrompt,
    selectSession: persistSelectedSessionId,
    createPlaySession,
    saveConfiguration,
    terminatePlaySession,
    compactPlaySession,
    submitSessionPrompt,
    cancelExecution,
    recordSubagentOutcome,
  };
}
