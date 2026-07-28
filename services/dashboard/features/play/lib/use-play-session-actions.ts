import {
  addSkill,
  answerUserQuestion,
  cancelJob,
  compactSession,
  createSession,
  deleteSession,
  getJob,
  getSession,
  listSessionMcps,
  removeSkill,
  setModelConfig,
  submitPrompt,
  terminateSession,
  updateSession,
} from "@/features/play/lib/client-api";
import { writeLastUsedDraft } from "@/features/play/lib/last-used-draft";
import { mergeJob } from "@/features/play/lib/play-session-events";
import { findMentionedSkillNames } from "@/features/play/lib/skill-mentions";
import {
  applyReasoningToGatewayOptions,
  buildDefaultSessionName,
  buildDraftFromSession,
  createNewSessionDraft,
  isSelectableSession,
  parseJsonObject,
  parseOptionalPositiveInteger,
} from "@/features/play/lib/session-draft";
import {
  ContextMetadata,
  DashboardConfig,
  JobDetail,
  ProviderResponse,
  SessionDetail,
  SessionDraft,
  SessionSummary,
  UserQuestionAnswerRequest,
} from "@/features/shared/lib/types";
import { Dispatch, RefObject, SetStateAction, useCallback } from "react";

interface UsePlaySessionActionsOptions {
  config: DashboardConfig | null;
  draft: SessionDraft | null;
  providers: ProviderResponse[];
  subagentChildSessionIds: Set<string>;
  selectedSession: SessionDetail | null;
  selectedSessionId: string | null;
  jobsCount: number;
  prompt: string;
  streamingJobId: string | null;
  cancelPending: boolean;
  refreshSessions: (preserveSelected?: boolean) => Promise<SessionSummary[]>;
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
  providers,
  subagentChildSessionIds,
  selectedSession,
  selectedSessionId,
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

    // Carry forward the user's last-used settings instead of resetting to
    // configuration defaults; fall back to defaults only when there is no
    // prior draft to copy from. Pass the current providers so a carried
    // provider that is now unavailable falls back to a working one.
    const nextDraft = createNewSessionDraft(config, draft, providers);

    setIsBusy(true);
    setErrorText(null);
    setStatusText("Creating session...");

    try {
      const created = await createSession(nextDraft.name, {
        context_recent_message_limit: parseOptionalPositiveInteger(
          nextDraft.recentMessageLimit,
          "Recent message limit"
        ),
        context_recent_tool_exchange_limit: parseOptionalPositiveInteger(
          nextDraft.recentToolExchangeLimit,
          "Recent tool exchange limit"
        ),
        default_subagent_persona: nextDraft.defaultSubagentPersona || null,
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

      // The settings that just created a session are the ones a later session
      // should inherit, including after a page reload.
      writeLastUsedDraft(nextDraft);

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
    providers,
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
        default_subagent_persona: draft.defaultSubagentPersona || null,
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

      const [refreshed, mcps] = await Promise.all([
        getSession(selectedSession.id),
        listSessionMcps(selectedSession.id),
      ]);
      const hydratedSession = { ...refreshed, mcps };
      setSelectedSession(hydratedSession);
      const savedDraft = buildDraftFromSession(config, hydratedSession);
      setDraft(savedDraft);
      writeLastUsedDraft(savedDraft);
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

  const removeSession = useCallback(
    async (sessionId: string) => {
      setIsBusy(true);
      setErrorText(null);
      setStatusText("Deleting session...");

      try {
        // A true delete, not a terminate: the orchestrator cancels any in-flight
        // job and then removes the session with its configuration and transcript,
        // so it never comes back in the list.
        await deleteSession(sessionId);
        // Refresh the shared sessions state so the deleted session actually
        // leaves the sidebar; reuse refreshSessions rather than fetching and
        // setting state separately.
        const remaining = await refreshSessions();
        if (sessionId === selectedSessionId) {
          // Reselect using the SAME predicate the sidebar uses (exclude
          // terminated sessions and subagent-child sessions) so selection never
          // lands on a session the sidebar hides.
          const nextSelectable = remaining.find((session) =>
            isSelectableSession(session, subagentChildSessionIds)
          );
          persistSelectedSessionId(nextSelectable?.id ?? null);
          if (!nextSelectable) {
            setSelectedSession(null);
          }
        }
        setStatusText("Session deleted");
      } catch (error) {
        setErrorText(
          error instanceof Error ? error.message : "Failed to delete session"
        );
        setStatusText("Delete failed");
      } finally {
        setIsBusy(false);
      }
    },
    [
      persistSelectedSessionId,
      refreshSessions,
      selectedSessionId,
      setErrorText,
      setIsBusy,
      setSelectedSession,
      setStatusText,
      subagentChildSessionIds,
    ]
  );

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
    // An `@` mention loads that skill's instructions into this turn. Matching
    // against the session's assigned skills is what separates a mention from
    // prose that merely contains an `@`, and the mention picker has already
    // attached whatever it offered.
    const mentionedSkills = findMentionedSkillNames(
      trimmedPrompt,
      selectedSession.skills.map((skill) => skill.skill_name)
    );

    try {
      const summary = await submitPrompt(
        selectedSession.id,
        trimmedPrompt,
        mentionedSkills
      );
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

  /**
   * Answer a question the model asked through `ask_user`.
   *
   * Errors are deliberately not routed through `setErrorText`: the question row
   * shows them inline (a 409 detail belongs next to the question it refers to),
   * so this rethrows for the caller instead of banner-ing it.
   */
  const answerJobQuestion = useCallback(
    async (
      jobId: string,
      questionId: string,
      body: UserQuestionAnswerRequest
    ) => {
      await answerUserQuestion(jobId, questionId, body);
      // The answer only becomes visible once the durable event list carries the
      // `user_question_answered` event; the stream normally delivers it, and
      // this refresh makes the flip immediate and survives a dropped stream.
      try {
        const refreshed = await getJob(jobId);
        setJobs((current) => mergeJob(current, refreshed));
      } catch {
        // Non-fatal: the stream still carries the answered event.
      }
    },
    [setJobs]
  );

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
    removeSession,
    compactPlaySession,
    submitSessionPrompt,
    answerJobQuestion,
    cancelExecution,
  };
}
