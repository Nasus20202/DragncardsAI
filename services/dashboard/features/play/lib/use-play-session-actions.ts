import {
  addMcp,
  addSkill,
  cancelJob,
  compactSession,
  createSession,
  getJob,
  getSession,
  listSessionMcps,
  removeMcp,
  removeSkill,
  setModelConfig,
  submitPrompt,
  terminateSession,
  updateSession,
} from "@/features/play/lib/client-api";
import { mergeJob } from "@/features/play/lib/play-session-events";
import {
  applyReasoningToGatewayOptions,
  buildDefaultSessionName,
  buildDraftFromSession,
  createDefaultDraft,
  parseCustomMcps,
  parseJsonObject,
  parseOptionalPositiveInteger,
} from "@/features/play/lib/session-draft";
import {
  ContextMetadata,
  DashboardConfig,
  JobDetail,
  SessionDetail,
  SessionDraft,
} from "@/features/shared/lib/types";
import { Dispatch, RefObject, SetStateAction, useCallback } from "react";

interface UsePlaySessionActionsOptions {
  config: DashboardConfig | null;
  draft: SessionDraft | null;
  selectedSession: SessionDetail | null;
  jobsCount: number;
  prompt: string;
  streamingJobId: string | null;
  cancelPending: boolean;
  refreshSessions: (preserveSelected?: boolean) => Promise<void>;
  persistSelectedSessionId: (id: string | null) => void;
  loadAllJobs: (sessionId: string) => Promise<JobDetail[]>;
  refreshContextMetadata: (sessionId: string) => Promise<void>;
  startStreaming: (jobId: string, afterId: string) => void;
  setSelectedSession: Dispatch<SetStateAction<SessionDetail | null>>;
  setDraft: Dispatch<SetStateAction<SessionDraft | null>>;
  setJobs: Dispatch<SetStateAction<JobDetail[]>>;
  setPrompt: Dispatch<SetStateAction<string>>;
  setStatusText: Dispatch<SetStateAction<string>>;
  setErrorText: Dispatch<SetStateAction<string | null>>;
  setIsBusy: Dispatch<SetStateAction<boolean>>;
  setIsCancellingExecution: Dispatch<SetStateAction<boolean>>;
  setContextMetadata: Dispatch<SetStateAction<ContextMetadata | null>>;
  committedModelRef: RefObject<{
    providerId: string;
    modelName: string;
  } | null>;
}

export function usePlaySessionActions({
  config,
  draft,
  selectedSession,
  jobsCount,
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
}: UsePlaySessionActionsOptions) {
  const createPlaySession = useCallback(async () => {
    if (!config || !draft) {
      return;
    }

    const nextDraft = createDefaultDraft(config);

    setIsBusy(true);
    setErrorText(null);
    setStatusText("Creating session...");

    try {
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
        parseJsonObject(nextDraft.gatewayOptionsText, "Gateway options"),
        nextDraft.reasoning
      );

      await setModelConfig(created.id, {
        provider_id: nextDraft.providerId,
        model_name: nextDraft.modelName,
        gateway_options: gatewayOptions,
        provider_options: parseJsonObject(
          nextDraft.providerOptionsText,
          "Provider options"
        ),
      });

      for (const skillName of nextDraft.selectedSkills) {
        await addSkill(created.id, skillName);
      }

      if (nextDraft.enableDefaultGameServiceMcp) {
        await addMcp(created.id, {
          name: config.defaultGameServiceMcpName,
          transport: config.defaultGameServiceMcpTransport,
          server_url: config.defaultGameServiceMcpUrl,
          headers: {},
        });
      }

      for (const mcp of parseCustomMcps(nextDraft.customMcpsText)) {
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
  }, [
    config,
    draft,
    persistSelectedSessionId,
    refreshSessions,
    setErrorText,
    setIsBusy,
    setStatusText,
  ]);

  const saveConfiguration = useCallback(async () => {
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
      const targetMcps = [
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
  }, [
    committedModelRef,
    config,
    draft,
    loadAllJobs,
    refreshContextMetadata,
    refreshSessions,
    selectedSession,
    setDraft,
    setErrorText,
    setIsBusy,
    setSelectedSession,
    setStatusText,
  ]);

  const terminatePlaySession = useCallback(async () => {
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
  }, [
    refreshSessions,
    selectedSession,
    setErrorText,
    setIsBusy,
    setSelectedSession,
    setStatusText,
  ]);

  const compactPlaySession = useCallback(async () => {
    if (!selectedSession) {
      return;
    }

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
  }, [
    loadAllJobs,
    selectedSession,
    setContextMetadata,
    setErrorText,
    setIsBusy,
    setStatusText,
  ]);

  const submitSessionPrompt = useCallback(async () => {
    if (!selectedSession || !prompt.trim()) {
      return;
    }

    setIsBusy(true);
    setErrorText(null);
    setStatusText("Submitting prompt...");

    const trimmedPrompt = prompt.trim();
    const isFirstPrompt = jobsCount === 0;

    try {
      const summary = await submitPrompt(selectedSession.id, trimmedPrompt);
      const nextJob = await getJob(summary.id);
      setJobs((current) => mergeJob(current, nextJob));
      startStreaming(nextJob.id, nextJob.latest_event_id ?? "0");
      setPrompt("");

      if (isFirstPrompt) {
        await updateSession(selectedSession.id, {
          name: trimmedPrompt.slice(0, 60),
        });
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
  }, [
    jobsCount,
    prompt,
    refreshSessions,
    selectedSession,
    setErrorText,
    setIsBusy,
    setJobs,
    setPrompt,
    setStatusText,
    startStreaming,
  ]);

  const cancelExecution = useCallback(async () => {
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
  }, [
    cancelPending,
    refreshSessions,
    setErrorText,
    setIsCancellingExecution,
    setJobs,
    setStatusText,
    streamingJobId,
  ]);

  return {
    createPlaySession,
    saveConfiguration,
    terminatePlaySession,
    compactPlaySession,
    submitSessionPrompt,
    cancelExecution,
  };
}
