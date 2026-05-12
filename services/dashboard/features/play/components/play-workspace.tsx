"use client";

import { Spinner } from "@heroui/react";
import {
  addMcp,
  addSkill,
  cancelJob,
  compactSession,
  createSession,
  fetchDashboardConfig,
  getContextMetadata,
  getJob,
  getSession,
  listAvailableSkills,
  listProviders,
  listSessionJobs,
  listSessionMcps,
  listSessions,
  removeMcp,
  removeSkill,
  setModelConfig,
  submitPrompt,
  terminateSession,
  updateSession,
} from "@/features/play/lib/client-api";
import {
  applyReasoningToGatewayOptions,
  buildDefaultSessionName,
  buildDraftFromSession,
  createDefaultDraft,
  parseCustomMcps,
  parseJsonObject,
  parseOptionalPositiveInteger,
} from "@/features/play/lib/session-draft";
import { mergeJob } from "@/features/play/lib/job-events";
import {
  deriveSubagentEntries,
  SubagentEntry,
} from "@/features/play/lib/subagents";
import { compareJobsOldestFirst } from "@/features/play/lib/transcript";
import { useJobStreaming } from "@/features/play/lib/use-job-streaming";
import {
  dedupeProviders,
  getMobileLayoutSnapshot,
  readSelectedSessionIdFromUrl,
  subscribeToMobileLayout,
  writeSelectedSessionIdToUrl,
} from "@/features/play/lib/workspace-state";
import { PlayConfigPanel } from "@/features/play/components/play-config-panel";
import { SubagentOutputModal } from "@/features/play/components/subagent-output-modal";
import { SubagentBurger } from "@/features/play/components/subagent-burger";
import { PlayPromptBox } from "@/features/play/components/play-prompt-box";
import { PlaySessionList } from "@/features/play/components/play-session-list";
import { PlayTranscript } from "@/features/play/components/play-transcript";
import {
  CustomMcpDraft,
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
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

export function PlayWorkspace() {
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
  const [draft, setDraft] = useState<SessionDraft | null>(null);
  /** All jobs for the selected session, sorted oldest-first. */
  const [jobs, setJobs] = useState<JobDetail[]>([]);
  /** DB statuses for child jobs, used to reconcile orphaned "running" subagent entries. */
  const [childJobStatuses, setChildJobStatuses] = useState<Map<string, string>>(
    new Map()
  );
  const [prompt, setPrompt] = useState("");
  const [statusText, setStatusText] = useState("Loading dashboard...");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [isCancellingExecution, setIsCancellingExecution] = useState(false);
  const [subagentModal, setSubagentModal] = useState<{
    childJobId: string;
    name: string;
  } | null>(null);
  const [contextMetadata, setContextMetadata] =
    useState<ContextMetadata | null>(null);
  /**
   * Tracks the provider/model currently committed to the open session.
   * Updated whenever a session loads so that the auto-sync effect can tell
   * the difference between "user changed the picker" and "draft was rebuilt
   * from the session" without triggering a redundant setModelConfig call.
   */
  const committedModelRef = useRef<{
    providerId: string;
    modelName: string;
  } | null>(null);

  const uniqueProviders = useMemo(
    () => dedupeProviders(providers),
    [providers]
  );

  const subagentEntries = useMemo<SubagentEntry[]>(() => {
    return deriveSubagentEntries(jobs, childJobStatuses);
  }, [jobs, childJobStatuses]);
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
  const isMobileLayout = useSyncExternalStore(
    subscribeToMobileLayout,
    getMobileLayoutSnapshot,
    () => false
  );
  const [sessionsCollapsedOverride, setSessionsCollapsedOverride] = useState<
    boolean | null
  >(null);
  const [settingsOpenOverride, setSettingsOpenOverride] = useState<
    boolean | null
  >(null);
  const isSessionsCollapsed = sessionsCollapsedOverride ?? isMobileLayout;
  const isSettingsOpen = settingsOpenOverride ?? !isMobileLayout;

  // Persist selected session across page reloads
  const persistSelectedSessionId = useCallback((id: string | null) => {
    setSelectedSessionId(id);
    writeSelectedSessionIdToUrl(id);
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

  /** Load ALL jobs for a session and set them as the transcript. */
  const loadAllJobs = useCallback(
    async (sessionId: string): Promise<JobDetail[]> => {
      const summary = await listSessionJobs(sessionId);
      const detailed = await Promise.all(
        summary.jobs.map((item) => getJob(item.id))
      );
      const sorted = [...detailed].sort(compareJobsOldestFirst);
      setJobs(sorted);

      // Reconcile orphaned subagent entries: fetch child job status for any
      // subagent_started entry that has no matching subagent_completed/failed.
      const started = new Set<string>();
      const resolved = new Set<string>();
      for (const job of sorted) {
        for (const event of job.events) {
          const p = event.payload as Record<string, unknown>;
          const childJobId =
            typeof p.child_job_id === "string" ? p.child_job_id : null;
          if (!childJobId) continue;
          if (event.event_type === "subagent_started") started.add(childJobId);
          if (
            event.event_type === "subagent_completed" ||
            event.event_type === "subagent_failed"
          )
            resolved.add(childJobId);
        }
      }
      const orphaned = [...started].filter((id) => !resolved.has(id));
      if (orphaned.length > 0) {
        const fetched = await Promise.allSettled(
          orphaned.map((id) => getJob(id))
        );
        const statusMap = new Map<string, string>();
        for (let i = 0; i < orphaned.length; i++) {
          const result = fetched[i];
          if (result.status === "fulfilled") {
            statusMap.set(orphaned[i], result.value.status);
          }
        }
        setChildJobStatuses(statusMap);
      } else {
        setChildJobStatuses(new Map());
      }

      return sorted;
    },
    []
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
        if (nextSessions.length > 0) {
          const sessionIdFromUrl = readSelectedSessionIdFromUrl();
          const savedId = localStorage.getItem("play:selectedSessionId");
          const restoredId =
            sessionIdFromUrl &&
            nextSessions.some((s) => s.id === sessionIdFromUrl)
              ? sessionIdFromUrl
              : savedId && nextSessions.some((s) => s.id === savedId)
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
  }, [persistSelectedSessionId]);

  useEffect(() => {
    if (!selectedSessionId || !config) {
      return;
    }

    const currentSessionId = selectedSessionId;
    const currentConfig = config;

    async function loadSession() {
      try {
        setStatusText("Loading session...");
        const nextSession = await getSession(currentSessionId);
        setSelectedSession(nextSession);
        const nextDraft = buildDraftFromSession(currentConfig, nextSession);
        setDraft(nextDraft);
        // Record the committed model so the auto-sync effect won't fire on load
        committedModelRef.current = {
          providerId: nextDraft.providerId,
          modelName: nextDraft.modelName,
        };

        const allJobs = await loadAllJobs(currentSessionId);
        void refreshContextMetadata(currentSessionId);

        // Resume streaming if the most-recent job is still running.
        // Start from 0 so the SSE endpoint replays all DB events first —
        // deduplication in appendStreamEvent prevents double-rendering.
        const newestJob = allJobs.at(-1); // oldest-first, so last = newest
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
    config,
    loadAllJobs,
    refreshContextMetadata,
    selectedSessionId,
    startStreaming,
    stopStreaming,
  ]);

  // When the provider changes, ensure the selected model is valid for the new provider.
  // If not, auto-switch to the first allowed model.
  useEffect(() => {
    if (!selectedProvider || !draft) return;
    const allowedModels = [...new Set(selectedProvider.models)].sort((a, b) =>
      a.localeCompare(b)
    );
    if (allowedModels.length > 0 && !allowedModels.includes(draft.modelName)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDraft((current) =>
        current ? { ...current, modelName: allowedModels[0] } : current
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft?.providerId, selectedProvider]);

  // When the draft's provider or model changes and differs from what the session
  // currently has committed, sync the change to the session automatically.
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft?.providerId, draft?.modelName, selectedSession]);

  async function handleCreateSession() {
    if (!config || !draft) {
      return;
    }

    setIsBusy(true);
    setErrorText(null);
    setStatusText("Creating session...");

    try {
      // Always use today's date for new sessions; the user can rename via Settings after creation.
      const created = await createSession(buildDefaultSessionName(), {
        context_recent_message_limit: parseOptionalPositiveInteger(
          draft.recentMessageLimit,
          "Recent message limit"
        ),
        context_recent_tool_exchange_limit: parseOptionalPositiveInteger(
          draft.recentToolExchangeLimit,
          "Recent tool exchange limit"
        ),
      });
      const gatewayOptions = applyReasoningToGatewayOptions(
        parseJsonObject(draft.gatewayOptionsText, "Gateway options"),
        draft.reasoning
      );

      await setModelConfig(created.id, {
        provider_id: draft.providerId,
        model_name: draft.modelName,
        gateway_options: gatewayOptions,
        provider_options: parseJsonObject(
          draft.providerOptionsText,
          "Provider options"
        ),
      });

      for (const skillName of draft.selectedSkills) {
        await addSkill(created.id, skillName);
      }

      if (draft.enableDefaultGameServiceMcp) {
        await addMcp(created.id, {
          name: config.defaultGameServiceMcpName,
          transport: config.defaultGameServiceMcpTransport,
          server_url: config.defaultGameServiceMcpUrl,
          headers: {},
        });
      }

      for (const mcp of parseCustomMcps(draft.customMcpsText)) {
        await addMcp(created.id, mcp);
      }

      await refreshSessions(false);
      persistSelectedSessionId(created.id);
      setStatusText("Session created");
    } catch (error) {
      setErrorText(
        error instanceof Error ? error.message : "Failed to create session"
      );
      setStatusText("Create failed");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleSaveConfiguration() {
    if (!selectedSession || !draft || !config) {
      return;
    }

    setIsBusy(true);
    setErrorText(null);
    setStatusText("Saving configuration...");

    try {
      const gatewayOptions = applyReasoningToGatewayOptions(
        parseJsonObject(draft.gatewayOptionsText, "Gateway options"),
        draft.reasoning
      );
      const providerOptions = parseJsonObject(
        draft.providerOptionsText,
        "Provider options"
      );
      const customMcps = parseCustomMcps(draft.customMcpsText);

      await updateSession(selectedSession.id, {
        name:
          draft.name.trim() ||
          selectedSession.name ||
          buildDefaultSessionName(),
        metadata: selectedSession.metadata,
        context_recent_message_limit: parseOptionalPositiveInteger(
          draft.recentMessageLimit,
          "Recent message limit"
        ),
        context_recent_tool_exchange_limit: parseOptionalPositiveInteger(
          draft.recentToolExchangeLimit,
          "Recent tool exchange limit"
        ),
      });
      await setModelConfig(selectedSession.id, {
        provider_id: draft.providerId,
        model_name: draft.modelName,
        gateway_options: gatewayOptions,
        provider_options: providerOptions,
      });

      const selectedSkillNames = new Set(draft.selectedSkills);
      for (const skill of selectedSession.skills) {
        if (!selectedSkillNames.has(skill.skill_name)) {
          await removeSkill(selectedSession.id, skill.skill_name);
        }
      }
      for (const skillName of selectedSkillNames) {
        if (
          !selectedSession.skills.some(
            (skill) => skill.skill_name === skillName
          )
        ) {
          await addSkill(selectedSession.id, skillName);
        }
      }

      const currentMcps = await listSessionMcps(selectedSession.id);
      const targetMcps: CustomMcpDraft[] = [
        ...(draft.enableDefaultGameServiceMcp
          ? [
              {
                name: config.defaultGameServiceMcpName,
                transport: config.defaultGameServiceMcpTransport,
                server_url: config.defaultGameServiceMcpUrl,
                headers: {},
              },
            ]
          : []),
        ...customMcps,
      ];

      for (const currentMcp of currentMcps) {
        if (!targetMcps.some((mcp) => mcp.name === currentMcp.name)) {
          await removeMcp(selectedSession.id, currentMcp.name);
        }
      }

      for (const mcp of targetMcps) {
        await addMcp(selectedSession.id, mcp);
      }

      const refreshed = await getSession(selectedSession.id);
      setSelectedSession(refreshed);
      const savedDraft = buildDraftFromSession(config, refreshed);
      setDraft(savedDraft);
      committedModelRef.current = {
        providerId: savedDraft.providerId,
        modelName: savedDraft.modelName,
      };
      await refreshSessions();
      await loadAllJobs(selectedSession.id);
      void refreshContextMetadata(selectedSession.id);
      setStatusText("Configuration saved");
    } catch (error) {
      setErrorText(
        error instanceof Error ? error.message : "Failed to save session"
      );
      setStatusText("Save failed");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleTerminateSession() {
    if (!selectedSession) {
      return;
    }

    setIsBusy(true);
    setErrorText(null);
    setStatusText("Terminating session...");

    try {
      await terminateSession(selectedSession.id);
      await refreshSessions();
      const refreshed = await getSession(selectedSession.id);
      setSelectedSession(refreshed);
      setStatusText("Session terminated");
    } catch (error) {
      setErrorText(
        error instanceof Error ? error.message : "Failed to terminate session"
      );
      setStatusText("Terminate failed");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCompact() {
    if (!selectedSession) return;
    setIsBusy(true);
    setErrorText(null);
    setStatusText("Compacting context...");
    try {
      const metadata = await compactSession(selectedSession.id);
      setContextMetadata(metadata);
      await loadAllJobs(selectedSession.id);
      setStatusText("Context compacted");
    } catch (error) {
      setErrorText(
        error instanceof Error ? error.message : "Compaction failed"
      );
      setStatusText("Compaction failed");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleSubmitPrompt() {
    if (!selectedSession || !prompt.trim()) {
      return;
    }

    setIsBusy(true);
    setErrorText(null);
    setStatusText("Submitting prompt...");

    const trimmedPrompt = prompt.trim();
    // Check before submission — if no non-compaction jobs yet, this is the first prompt
    // Check before submission — if no jobs yet, this is the first prompt
    const isFirstPrompt = jobs.length === 0;

    try {
      const summary = await submitPrompt(selectedSession.id, trimmedPrompt);
      const nextJob = await getJob(summary.id);
      // Add the new job to the existing list immediately (no wipe)
      setJobs((current) => mergeJob(current, nextJob));
      startStreaming(nextJob.id, nextJob.latest_event_id ?? "0");
      setPrompt("");

      // Auto-title the session from the first prompt
      if (isFirstPrompt) {
        const autoName = trimmedPrompt.slice(0, 60);
        await updateSession(selectedSession.id, { name: autoName });
      }

      await refreshSessions();
      setStatusText("Prompt submitted");
    } catch (error) {
      setErrorText(
        error instanceof Error ? error.message : "Prompt submission failed"
      );
      setStatusText("Prompt failed");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleCancelExecution() {
    if (!streamingJobId || cancelPending) {
      return;
    }

    setIsCancellingExecution(true);
    setErrorText(null);
    setStatusText("Requesting cancellation...");

    try {
      const cancelledJob = await cancelJob(streamingJobId);
      setJobs((current) =>
        current.map((job) =>
          job.id === cancelledJob.id ? { ...job, ...cancelledJob } : job
        )
      );
      await refreshSessions();
      setStatusText("Cancellation requested");
    } catch (error) {
      setErrorText(
        error instanceof Error ? error.message : "Failed to cancel execution"
      );
      setStatusText("Cancel failed");
    } finally {
      setIsCancellingExecution(false);
    }
  }

  if (!draft || !config) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="relative flex h-full overflow-hidden">
      {streamState === "streaming" ? (
        <div
          aria-live="polite"
          aria-label="Streaming response"
          className="pointer-events-none absolute inset-x-0 top-4 z-20 flex justify-center px-4"
          role="status"
        >
          <div className="flex items-center gap-3 rounded-full border border-default-200/60 bg-background/90 px-4 py-2 shadow-lg backdrop-blur-sm">
            <Spinner size="sm" />
            <span className="text-sm text-default-500">
              Streaming response...
            </span>
          </div>
        </div>
      ) : null}
      {/* Left — session sidebar */}
      <aside
        data-testid="session-sidebar"
        className={`flex shrink-0 flex-col border-r border-default-200/60 bg-background transition-all duration-200 ${
          isSessionsCollapsed ? "w-11 sm:w-14" : "w-56"
        }`}
      >
        <PlaySessionList
          canCreate={Boolean(draft)}
          isCollapsed={isSessionsCollapsed}
          isBusy={isBusy}
          selectedSessionId={selectedSessionId}
          streamingSessionId={streamingJobId ? selectedSessionId : null}
          sessions={sessions.filter(
            (s) => !subagentEntries.some((e) => e.childSessionId === s.id)
          )}
          onCreate={handleCreateSession}
          onToggleCollapsed={() =>
            setSessionsCollapsedOverride(
              (current) => !(current ?? isMobileLayout)
            )
          }
          onSelect={persistSelectedSessionId}
        />
      </aside>

      {/* Centre — chat */}
      <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        {subagentEntries.length > 0 && (
          <div className="pointer-events-none absolute right-3 top-14 z-10 flex max-w-[calc(100%-1.5rem)] justify-end sm:right-4">
            <div className="pointer-events-auto">
              <SubagentBurger
                entries={subagentEntries}
                onSelect={(entry) =>
                  setSubagentModal({
                    childJobId: entry.childJobId,
                    name: entry.name ?? entry.childJobId.slice(0, 8),
                  })
                }
                onSubagentFinished={(childJobId, outcome) => {
                  setChildJobStatuses((prev) => {
                    const next = new Map(prev);
                    next.set(childJobId, outcome);
                    return next;
                  });
                }}
              />
            </div>
          </div>
        )}
        <PlayTranscript
          errorText={errorText}
          isBusy={isBusy}
          jobs={jobs}
          streamingJobId={streamingJobId}
          selectedSession={selectedSession}
          statusText={statusText}
          streamState={streamState}
          onOpenSettings={() =>
            setSettingsOpenOverride((current) => !(current ?? !isMobileLayout))
          }
          settingsOpen={isSettingsOpen}
        />
        <PlayPromptBox
          activeJobId={streamingJobId}
          cancelPending={cancelPending}
          contextMetadata={contextMetadata}
          isBusy={isBusy}
          prompt={prompt}
          selectedSession={selectedSession}
          onCancelExecution={handleCancelExecution}
          onCompact={handleCompact}
          onPromptChange={setPrompt}
          onSubmit={handleSubmitPrompt}
        />
      </div>

      {/* Right — settings panel (inline collapsible) */}
      <PlayConfigPanel
        canSave={Boolean(selectedSession)}
        draft={draft}
        isBusy={isBusy}
        isOpen={isSettingsOpen}
        modelOptions={modelOptions}
        providers={uniqueProviders}
        skills={skills}
        onClose={() => setSettingsOpenOverride(false)}
        onDraftChange={setDraft}
        onSave={handleSaveConfiguration}
        onTerminate={handleTerminateSession}
      />

      {subagentModal && (
        <SubagentOutputModal
          key={subagentModal.childJobId}
          childJobId={subagentModal.childJobId}
          name={subagentModal.name}
          isRunning={
            subagentEntries.find(
              (e) => e.childJobId === subagentModal.childJobId
            )?.status === "running"
          }
          onClose={() => setSubagentModal(null)}
        />
      )}
    </div>
  );
}
