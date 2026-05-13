"use client";

import { Spinner } from "@heroui/react";
import { usePlaySession } from "@/features/play/lib/use-play-session";
import {
  getMobileLayoutSnapshot,
  subscribeToMobileLayout,
} from "@/features/play/lib/workspace-state";
import { PlayConfigPanel } from "@/features/play/components/play-config-panel";
import { SubagentOutputModal } from "@/features/play/components/subagent-output-modal";
import { SubagentList } from "@/features/play/components/subagent-list";
import { PlayPromptBox } from "@/features/play/components/play-prompt-box";
import { PlaySessionList } from "@/features/play/components/play-session-list";
import { PlayTranscript } from "@/features/play/components/play-transcript";
import { useState, useSyncExternalStore } from "react";

export function PlayWorkspace() {
  const {
    config,
    draft,
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
    selectSession,
    createPlaySession,
    saveConfiguration,
    terminatePlaySession,
    compactPlaySession,
    submitSessionPrompt,
    cancelExecution,
    recordSubagentOutcome,
  } = usePlaySession();
  const [subagentModal, setSubagentModal] = useState<{
    childJobId: string;
    name: string;
  } | null>(null);
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

  if (!draft || !config) {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <div
      data-testid="play-workspace"
      className="relative flex h-full overflow-hidden"
    >
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
          onCreate={createPlaySession}
          onToggleCollapsed={() =>
            setSessionsCollapsedOverride(
              (current) => !(current ?? isMobileLayout)
            )
          }
          onSelect={selectSession}
        />
      </aside>

      {/* Centre — chat */}
      <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden">
        {subagentEntries.length > 0 && (
          <div className="pointer-events-none absolute right-3 top-14 z-10 flex max-w-[calc(100%-1.5rem)] justify-end sm:right-4">
            <div className="pointer-events-auto">
              <SubagentList
                entries={subagentEntries}
                onSelect={(entry) =>
                  setSubagentModal({
                    childJobId: entry.childJobId,
                    name: entry.name ?? entry.childJobId.slice(0, 8),
                  })
                }
                onSubagentFinished={recordSubagentOutcome}
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
          onCancelExecution={cancelExecution}
          onCompact={compactPlaySession}
          onPromptChange={setPrompt}
          onSubmit={submitSessionPrompt}
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
        onSave={saveConfiguration}
        onTerminate={terminatePlaySession}
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
