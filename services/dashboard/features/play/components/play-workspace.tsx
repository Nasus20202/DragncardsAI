"use client";

import { Spinner } from "@heroui/react";
import {
  addMcp,
  addSkill,
  compactSession,
  createGameSession,
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
  buildDraftFromSession,
  createDefaultDraft,
  parseCustomMcps,
  parseJsonObject,
} from "@/features/play/lib/session-draft";
import { compareJobsOldestFirst } from "@/features/play/lib/transcript";
import { PlayConfigPanel } from "@/features/play/components/play-config-panel";
import { PlayPromptBox } from "@/features/play/components/play-prompt-box";
import { PlaySessionList } from "@/features/play/components/play-session-list";
import { PlayTranscript } from "@/features/play/components/play-transcript";
import {
  CustomMcpDraft,
  ContextMetadata,
  DashboardConfig,
  JobDetail,
  JobEventResponse,
  JsonValue,
  ProviderResponse,
  SessionDetail,
  SessionDraft,
  SessionSummary,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

function dedupeProviders(providers: ProviderResponse[]) {
  const byId = new Map<string, ProviderResponse>();
  for (const provider of providers) {
    if (!byId.has(provider.provider_id)) {
      byId.set(provider.provider_id, provider);
    }
  }
  return Array.from(byId.values());
}

/** Merge a new or updated JobDetail into an existing sorted jobs array. */
function mergeJob(jobs: JobDetail[], updated: JobDetail): JobDetail[] {
  const existing = jobs.findIndex((j) => j.id === updated.id);
  if (existing >= 0) {
    const next = [...jobs];
    next[existing] = updated;
    return next;
  }
  return [...jobs, updated].sort(compareJobsOldestFirst);
}

export function PlayWorkspace() {
  const [config, setConfig] = useState<DashboardConfig | null>(null);
  const [providers, setProviders] = useState<ProviderResponse[]>([]);
  const [skills, setSkills] = useState<SkillDefinitionResponse[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<SessionDetail | null>(null);
  const [draft, setDraft] = useState<SessionDraft | null>(null);
  /** All jobs for the selected session, sorted oldest-first. */
  const [jobs, setJobs] = useState<JobDetail[]>([]);
  /** ID of the job currently being streamed, so appendStreamEvent knows which to update. */
  const streamingJobIdRef = useRef<string | null>(null);
  const [streamingJobId, setStreamingJobId] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [statusText, setStatusText] = useState("Loading dashboard...");
  const [errorText, setErrorText] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [streamState, setStreamState] = useState<"idle" | "streaming">("idle");
  const [contextMetadata, setContextMetadata] = useState<ContextMetadata | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  /**
   * Tracks the provider/model currently committed to the open session.
   * Updated whenever a session loads so that the auto-sync effect can tell
   * the difference between "user changed the picker" and "draft was rebuilt
   * from the session" without triggering a redundant setModelConfig call.
   */
  const committedModelRef = useRef<{ providerId: string; modelName: string } | null>(null);

  const uniqueProviders = useMemo(() => dedupeProviders(providers), [providers]);
  const selectedProvider = useMemo(
    () => uniqueProviders.find((provider) => provider.provider_id === draft?.providerId) ?? null,
    [draft?.providerId, uniqueProviders],
  );
  const modelOptions = useMemo(() => {
    const models = selectedProvider?.models ?? [];
    return [...new Set(models)].sort((left, right) => left.localeCompare(right));
  }, [selectedProvider]);
  const [isSessionsCollapsed, setIsSessionsCollapsed] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(true);

  // Persist selected session across page reloads
  const persistSelectedSessionId = useCallback((id: string | null) => {
    setSelectedSessionId(id);
    if (id) {
      localStorage.setItem("play:selectedSessionId", id);
    } else {
      localStorage.removeItem("play:selectedSessionId");
    }
  }, []);

  const stopStreaming = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    streamingJobIdRef.current = null;
    setStreamingJobId(null);
    setStreamState("idle");
  }, []);

  const appendStreamEvent = useCallback((payload: JobEventResponse) => {
    const jobId = streamingJobIdRef.current;
    if (!jobId) return;

    setJobs((current) => {
      const idx = current.findIndex((j) => j.id === jobId);
      if (idx < 0) return current;
      const job = current[idx];

      // Exact duplicate — skip
      if (job.events.some((e) => e.id === payload.id)) return current;

      const isTerminal = ["completion", "failure", "cancellation"].includes(payload.event_type);
      let nextEvents: JobEventResponse[];

      // Live streaming chunks (model_output/reasoning with stream=true) update the
      // existing snapshot row in-place rather than appending a new event.
      // This avoids doubling text when the DB snapshot is already loaded.
      const isStreamChunk =
        (payload.event_type === "model_output" || payload.event_type === "reasoning") &&
        payload.payload.stream === true;

      if (isStreamChunk) {
        const snapshotIdx = [...job.events].reverse().findIndex(
          (e) => e.event_type === payload.event_type,
        );
        const realIdx = snapshotIdx >= 0 ? job.events.length - 1 - snapshotIdx : -1;
        if (realIdx >= 0) {
          // Append chunk text onto the snapshot event
          const snapshot = job.events[realIdx];
          const prevText = typeof snapshot.payload.text === "string" ? snapshot.payload.text : "";
          const newText = typeof payload.payload.text === "string" ? payload.payload.text : "";
          const updated: JobEventResponse = {
            ...snapshot,
            payload: { ...snapshot.payload, text: prevText + newText },
          };
          nextEvents = [...job.events];
          nextEvents[realIdx] = updated;
        } else {
          // No snapshot yet — treat as a new non-stream event
          const newPayload: Record<string, JsonValue> = { ...payload.payload };
          delete newPayload.stream;
          nextEvents = [...job.events, { ...payload, payload: newPayload }]
            .sort((l, r) => new Date(l.created_at).getTime() - new Date(r.created_at).getTime());
        }
      } else {
        nextEvents = [...job.events, payload].sort(
          (l, r) => new Date(l.created_at).getTime() - new Date(r.created_at).getTime(),
        );
      }

      const updatedJob: JobDetail = {
        ...job,
        events: nextEvents,
        latest_event_id: payload.id,
        latest_event_type: payload.event_type,
        status: isTerminal
          ? payload.event_type === "completion"
            ? "completed"
            : payload.event_type === "cancellation"
              ? "cancelled"
              : payload.event_type
          : job.status,
        outputs:
          payload.event_type === "completion" && typeof payload.payload.text === "string"
            ? [payload.payload.text, ...job.outputs].filter(Boolean)
            : job.outputs,
      };
      const next = [...current];
      next[idx] = updatedJob;
      return next;
    });
  }, []);

  /** Load ALL jobs for a session and set them as the transcript. */
  const loadAllJobs = useCallback(async (sessionId: string): Promise<JobDetail[]> => {
    const summary = await listSessionJobs(sessionId);
    const detailed = await Promise.all(summary.jobs.map((item) => getJob(item.id)));
    const sorted = [...detailed].sort(compareJobsOldestFirst);
    setJobs(sorted);
    return sorted;
  }, []);

  const refreshContextMetadata = useCallback(async (sessionId: string) => {
    try {
      const metadata = await getContextMetadata(sessionId);
      setContextMetadata(metadata);
    } catch {
      // Non-fatal: ignore metadata fetch errors
    }
  }, []);

  const startStreaming = useCallback(
    (jobId: string, afterId: string) => {
      stopStreaming();
      streamingJobIdRef.current = jobId;
      setStreamingJobId(jobId);
      const source = new EventSource(`/api/proxy/orchestrator/jobs/${jobId}/events/stream?after=${afterId}`);
      eventSourceRef.current = source;
      setStreamState("streaming");

      const handleEvent = (event: MessageEvent<string>) => {
        const payload = JSON.parse(event.data) as JobEventResponse;
        appendStreamEvent(payload);
        if (["completion", "failure", "cancellation"].includes(payload.event_type)) {
          stopStreaming();
          if (selectedSessionId) {
            void refreshContextMetadata(selectedSessionId);
          }
        }
      };

      source.addEventListener("progress", handleEvent as EventListener);
      source.addEventListener("reasoning", handleEvent as EventListener);
      source.addEventListener("model_output", handleEvent as EventListener);
      source.addEventListener("tool_call", handleEvent as EventListener);
      source.addEventListener("tool_result", handleEvent as EventListener);
      source.addEventListener("completion", handleEvent as EventListener);
      source.addEventListener("failure", handleEvent as EventListener);
      source.addEventListener("cancellation", handleEvent as EventListener);
      source.onmessage = handleEvent;
      source.onerror = () => {
        stopStreaming();
      };
    },
    [appendStreamEvent, stopStreaming, selectedSessionId, refreshContextMetadata],
  );

  useEffect(() => {
    async function load() {
      try {
        const [nextConfig, nextProviders, nextSkills, nextSessions] = await Promise.all([
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
          const savedId = localStorage.getItem("play:selectedSessionId");
          const restoredId =
            savedId && nextSessions.some((s) => s.id === savedId) ? savedId : nextSessions[0].id;
          setSelectedSessionId(restoredId);
        }
      } catch (error) {
        setErrorText(error instanceof Error ? error.message : "Failed to load dashboard");
        setStatusText("Configuration error");
      }
    }

    void load();
  }, []);

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
        setErrorText(error instanceof Error ? error.message : "Failed to load session");
        setStatusText("Session load failed");
      }
    }

    void loadSession();

    return () => {
      stopStreaming();
    };
  }, [config, loadAllJobs, selectedSessionId, startStreaming, stopStreaming]);

  // When the provider changes, ensure the selected model is valid for the new provider.
  // If not, auto-switch to the first allowed model.
  useEffect(() => {
    if (!selectedProvider || !draft) return;
    const allowedModels = [...new Set(selectedProvider.models)].sort((a, b) => a.localeCompare(b));
    if (allowedModels.length > 0 && !allowedModels.includes(draft.modelName)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDraft((current) =>
        current ? { ...current, modelName: allowedModels[0] } : current,
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
    committedModelRef.current = { providerId: draft.providerId, modelName: draft.modelName };
    void setModelConfig(selectedSession.id, {
      provider_id: draft.providerId,
      model_name: draft.modelName,
      gateway_options: (selectedSession.model_config?.gateway_options as Record<string, JsonValue>) ?? {},
      provider_options: (selectedSession.model_config?.provider_options as Record<string, JsonValue>) ?? {},
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft?.providerId, draft?.modelName, selectedSession]);

  async function refreshSessions(preserveSelected = true) {
    const nextSessions = await listSessions();
    setSessions(nextSessions);
    if (!preserveSelected && nextSessions.length > 0) {
      persistSelectedSessionId(nextSessions[0].id);
    }
  }

  async function handleCreateSession() {
    if (!config || !draft) {
      return;
    }

    setIsBusy(true);
    setErrorText(null);
    setStatusText("Creating session...");

    try {
      const defaultName = new Date().toLocaleString("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).replace(",", "");
      // Always use today's date for new sessions; the user can rename via Settings after creation.
      const created = await createSession(defaultName);
      const gatewayOptions = applyReasoningToGatewayOptions(
        parseJsonObject(draft.gatewayOptionsText, "Gateway options"),
        draft.reasoning,
      );

      await setModelConfig(created.id, {
        provider_id: draft.providerId,
        model_name: draft.modelName,
        gateway_options: gatewayOptions,
        provider_options: parseJsonObject(draft.providerOptionsText, "Provider options"),
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

      if (draft.createGameSession) {
        const gameSession = await createGameSession(draft.gamePluginName);
        await updateSession(created.id, {
          metadata: {
            game_session: {
              ...gameSession,
              frontend_url: `${config.dragncardsFrontendUrl.replace(/\/$/, "")}/room/${gameSession.room_slug}`,
            },
          },
        });
      }

      await refreshSessions(false);
      persistSelectedSessionId(created.id);
      setStatusText("Session created");
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "Failed to create session");
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
        draft.reasoning,
      );
      const providerOptions = parseJsonObject(draft.providerOptionsText, "Provider options");
      const customMcps = parseCustomMcps(draft.customMcpsText);

      await updateSession(selectedSession.id, {
        name: draft.name.trim() || selectedSession.name || new Date().toLocaleString("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).replace(",", ""),
        metadata: selectedSession.metadata,
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
        if (!selectedSession.skills.some((skill) => skill.skill_name === skillName)) {
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
      committedModelRef.current = { providerId: savedDraft.providerId, modelName: savedDraft.modelName };
      await refreshSessions();
      await loadAllJobs(selectedSession.id);
      setStatusText("Configuration saved");
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "Failed to save session");
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
      setErrorText(error instanceof Error ? error.message : "Failed to terminate session");
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
      setStatusText("Context compacted");
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "Compaction failed");
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

    try {
      const summary = await submitPrompt(selectedSession.id, prompt.trim());
      const nextJob = await getJob(summary.id);
      // Add the new job to the existing list immediately (no wipe)
      setJobs((current) => mergeJob(current, nextJob));
      startStreaming(nextJob.id, nextJob.latest_event_id ?? "0");
      setPrompt("");
      await refreshSessions();
      setStatusText("Prompt submitted");
    } catch (error) {
      setErrorText(error instanceof Error ? error.message : "Prompt submission failed");
      setStatusText("Prompt failed");
    } finally {
      setIsBusy(false);
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
    <div className="flex h-full overflow-hidden">
      {/* Left — session sidebar */}
      <aside
        className={`flex shrink-0 flex-col border-r border-default-200/60 bg-background transition-all duration-200 ${
          isSessionsCollapsed ? "w-14" : "w-56"
        }`}
      >
        <PlaySessionList
          canCreate={Boolean(draft)}
          isCollapsed={isSessionsCollapsed}
          isBusy={isBusy}
          selectedSessionId={selectedSessionId}
          sessions={sessions}
          onCreate={handleCreateSession}
          onToggleCollapsed={() => setIsSessionsCollapsed((c) => !c)}
          onSelect={persistSelectedSessionId}
        />
      </aside>

      {/* Centre — chat */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <PlayTranscript
          errorText={errorText}
          isBusy={isBusy}
          jobs={jobs}
          streamingJobId={streamingJobId}
          selectedSession={selectedSession}
          statusText={statusText}
          streamState={streamState}
          onOpenSettings={() => setIsSettingsOpen((o) => !o)}
          settingsOpen={isSettingsOpen}
        />
        <PlayPromptBox
          contextMetadata={contextMetadata}
          isBusy={isBusy}
          prompt={prompt}
          selectedSession={selectedSession}
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
        onClose={() => setIsSettingsOpen(false)}
        onDraftChange={setDraft}
        onSave={handleSaveConfiguration}
        onTerminate={handleTerminateSession}
      />
    </div>
  );
}
