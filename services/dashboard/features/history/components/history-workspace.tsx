"use client";

import { Button, Spinner } from "@heroui/react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  DashboardConfig,
  HistoryGame,
  ProviderResponse,
  RestoreMode,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";
import {
  fetchDashboardConfig,
  listAvailableSkills,
  listProviders,
  listSessions,
} from "@/features/play/lib/client-api";
import {
  deleteHistoryGame,
  listHistoryGames,
  restoreGame,
} from "@/features/history/lib/history-api";
import {
  JudgeDraft,
  createDefaultJudgeDraft,
  reconcileProviderModel,
} from "@/features/history/lib/judge-config";
import { RightDrawer } from "@/features/shared/components/right-drawer";
import { mapSessionGameNames } from "@/features/history/lib/history-games";
import { useHistory } from "@/features/history/lib/use-history";
import { useBoardReconstruction } from "@/features/history/lib/use-board-reconstruction";
import { useEvaluationQueue } from "@/features/history/lib/use-evaluation-queue";
import { HistoryGamesList } from "@/features/history/components/history-games-list";
import { HistoryNavTree } from "@/features/history/components/history-nav-tree";
import { HistoryTranscript } from "@/features/history/components/history-transcript";
import { EvaluationControl } from "@/features/history/components/evaluation-control";
import { EvaluationQueue } from "@/features/history/components/evaluation-queue";
import { HistoryScorecard } from "@/features/history/components/history-scorecard";
import {
  HistoryTransferControls,
  TransferNotice,
} from "@/features/history/components/history-transfer";
import { BoardView } from "@/features/history/components/board-control";

export function HistoryWorkspace({
  initialGameId = null,
}: {
  initialGameId?: string | null;
}) {
  const [games, setGames] = useState<HistoryGame[]>([]);
  const [gameId, setGameId] = useState<string | null>(initialGameId);
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null);
  const [lastGameId, setLastGameId] = useState<string | null>(initialGameId);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteTargetId, setDeleteTargetId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  // Outcome of the last export/import, shown in a notice row under the header
  // (the dashboard surfaces results inline; there is no toast layer).
  const [transferNotice, setTransferNotice] = useState<TransferNotice | null>(
    null
  );
  // Evaluation is a game-level action (it can target the whole game, not just
  // the selected move), so it lives in its own drawer.
  const [evalOpen, setEvalOpen] = useState(false);
  // The persistent, cross-game evaluations queue (open state). The queue itself
  // is derived from the polled eval-service listing, not stored here.
  const [queueOpen, setQueueOpen] = useState(false);
  // The per-player game scorecard drawer (open state); derived from `events`.
  const [scorecardOpen, setScorecardOpen] = useState(false);
  // Transcript usability controls: a global expand/collapse pulse (bumping
  // `generation` forces every event body open/closed) and a search query.
  const [expandSignal, setExpandSignal] = useState({
    generation: 0,
    expanded: false,
  });
  const [searchQuery, setSearchQuery] = useState("");
  // Reveal pulse: selecting via the nav tree also opens the target event's body.
  const [reveal, setReveal] = useState({
    seq: null as number | null,
    mode: "body" as "body" | "evals",
    nonce: 0,
  });
  const navigateToEvent = (seq: number) => {
    setSelectedSeq(seq);
    setReveal((r) => ({ seq, mode: "body", nonce: r.nonce + 1 }));
  };

  // Judge-config sources + draft (Play-parity). Loaded best-effort; the panel
  // is hidden until a draft exists.
  const [providers, setProviders] = useState<ProviderResponse[]>([]);
  const [skills, setSkills] = useState<SkillDefinitionResponse[]>([]);
  const [judgeDraft, setJudgeDraft] = useState<JudgeDraft | null>(null);
  // DragnCards frontend base URL for embedding reconstructed boards.
  const [frontendUrl, setFrontendUrl] = useState<string>("");
  // game_id -> friendly session name (from agent-orchestrator sessions, whose
  // metadata.game_id links back to a history game). Lets the list show a
  // readable label instead of the raw session UUID.
  const [gameNames, setGameNames] = useState<Record<string, string>>({});

  // Clear the selection when the game changes (reset-on-change during render).
  if (gameId !== lastGameId) {
    setLastGameId(gameId);
    setSelectedSeq(null);
  }

  const refreshGames = (preferId?: string | null) => {
    return listHistoryGames()
      .then((loaded) => {
        setGames(loaded);
        const stillExists =
          preferId !== undefined
            ? loaded.some((game) => game.game_id === preferId)
            : loaded.some((game) => game.game_id === gameId);
        if (!stillExists && !gameId && loaded.length > 0) {
          setGameId(loaded[0].game_id);
        }
        return loaded;
      })
      .catch(() => {
        /* listing is best-effort; the transcript still works with a known id */
        return [] as HistoryGame[];
      });
  };

  useEffect(() => {
    let cancelled = false;
    listHistoryGames()
      .then((loaded) => {
        if (cancelled) return;
        setGames(loaded);
        if (!gameId && loaded.length > 0) {
          setGameId(loaded[0].game_id);
        }
      })
      .catch(() => {
        /* listing is best-effort; the transcript still works with a known id */
      });

    // Map game_id -> friendly session name from orchestrator sessions, so the
    // list can show a readable label. Best-effort: falls back to the UUID.
    listSessions()
      .then((sessions) => {
        if (cancelled) return;
        setGameNames(mapSessionGameNames(sessions));
      })
      .catch(() => {
        /* naming is best-effort; the list falls back to the game id */
      });

    // Load judge-config sources in parallel; reconcile provider/model against
    // what's actually available, mirroring Play's initial draft.
    Promise.all([
      fetchDashboardConfig(),
      listProviders().catch(() => [] as ProviderResponse[]),
      listAvailableSkills().catch(() => [] as SkillDefinitionResponse[]),
    ])
      .then(
        ([config, loadedProviders, loadedSkills]: [
          DashboardConfig,
          ProviderResponse[],
          SkillDefinitionResponse[],
        ]) => {
          if (cancelled) return;
          setProviders(loadedProviders);
          setSkills(loadedSkills);
          setFrontendUrl(config.dragncardsFrontendUrl);
          const base = createDefaultJudgeDraft(config);
          const { providerId, modelName } = reconcileProviderModel(
            loadedProviders,
            base.providerId,
            base.modelName
          );
          setJudgeDraft({ ...base, providerId, modelName });
        }
      )
      .catch(() => {
        /* judge config is optional; without it requests use server defaults */
      });

    return () => {
      cancelled = true;
    };
    // Only run on mount: we seed the default selection once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { events, isLoading, error, isTruncated, reload } = useHistory(gameId);

  // The selected game's summary carries the authoritative recorded event count,
  // which is what the truncation notice compares the loaded events against.
  const selectedGame = games.find((game) => game.game_id === gameId) ?? null;

  // Persistent evaluations queue: polls the cross-game listing while the panel
  // is open or anything is in flight, and refreshes the transcript whenever a
  // request settles so per-move verdicts surface as they land.
  const queue = useEvaluationQueue(queueOpen, reload);

  // On-demand "board at this event" reconstruction (ephemeral, single live).
  const board = useBoardReconstruction(gameId, selectedSeq);

  // Keep history live without a manual reload: refresh the games list, friendly
  // names, and the selected game's events whenever this tab regains focus or
  // visibility (e.g. switching back from the Play tab), plus a slow poll while
  // the tab is visible. History is append-only, so re-fetching is cheap and
  // never disturbs the current selection.
  useEffect(() => {
    const refresh = () => {
      if (
        typeof document !== "undefined" &&
        document.visibilityState !== "visible"
      ) {
        return;
      }
      listHistoryGames()
        .then(setGames)
        .catch(() => {});
      listSessions()
        .then((sessions) => setGameNames(mapSessionGameNames(sessions)))
        .catch(() => {});
      reload();
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    const interval = window.setInterval(refresh, 15000);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
      window.clearInterval(interval);
    };
  }, [reload]);

  // `handleRestore` and the transcript's `board` bundle below are handed to every
  // event row, so both are kept referentially stable — a fresh function or object
  // literal per render would re-render the whole transcript (see the memoised
  // `TranscriptEvent`).
  const handleRestore = useCallback(
    async (targetSeq: number, mode: RestoreMode) => {
      if (!gameId) {
        throw new Error("No game selected.");
      }
      const outcome = await restoreGame(gameId, {
        target_seq: targetSeq,
        mode,
      });
      // A new-session restore does not alter this timeline; an in-place restore
      // does, so refresh the events afterwards.
      if (mode === "in_place") {
        reload();
      }
      return outcome;
    },
    [gameId, reload]
  );

  // Destructured so the memo depends on the individual values rather than on the
  // hook's result object, whose identity changes on every render.
  const {
    isOpening: boardIsOpening,
    error: boardError,
    reconstruction: boardReconstruction,
    open: openBoard,
  } = board;
  const transcriptBoard = useMemo(
    () => ({
      gameId,
      isOpening: boardIsOpening,
      error: boardError,
      isOpen: boardReconstruction !== null,
      onOpen: () => void openBoard(),
    }),
    [gameId, boardIsOpening, boardError, boardReconstruction, openBoard]
  );

  const openDelete = (id: string) => {
    setDeleteTargetId(id);
    setDeleteError(null);
    setConfirmDelete(true);
  };

  const handleDelete = async () => {
    if (!deleteTargetId) return;
    const removedId = deleteTargetId;
    const wasActive = removedId === gameId;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deleteHistoryGame(removedId);
      setConfirmDelete(false);
      // Clear the active selection only if we deleted the game in view.
      if (wasActive) {
        setGameId(null);
      }
      setDeleteTargetId(null);
      await refreshGames(wasActive ? null : gameId);
    } catch (e) {
      setDeleteError(
        e instanceof Error ? e.message : "Failed to delete history."
      );
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center gap-3 border-b border-default-200/60 px-4 py-2">
        <h1 className="text-sm font-semibold text-foreground">Game history</h1>
        {isLoading && <Spinner size="sm" />}
        <div className="ml-auto flex items-center gap-2">
          <HistoryTransferControls
            gameId={gameId}
            onNotice={setTransferNotice}
            onImported={(importedId) => {
              setGameId(importedId);
              void refreshGames(importedId);
            }}
          />
          <Button
            type="button"
            size="sm"
            variant="secondary"
            data-testid="history-eval-queue-open"
            onPress={() => setQueueOpen(true)}
          >
            Evaluations
            {queue.activeCount > 0 && (
              <span
                data-testid="history-eval-queue-badge"
                className="ml-1.5 inline-flex min-w-5 items-center justify-center rounded-full bg-accent px-1.5 text-xs font-semibold text-accent-foreground"
              >
                {queue.activeCount}
              </span>
            )}
          </Button>
          {gameId && (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              data-testid="history-scorecard-open"
              onPress={() => setScorecardOpen(true)}
            >
              Scorecard
            </Button>
          )}
          {gameId && (
            <Button
              type="button"
              size="sm"
              variant="primary"
              data-testid="history-evaluate-open"
              onPress={() => setEvalOpen(true)}
            >
              Evaluate
            </Button>
          )}
        </div>
      </header>

      {transferNotice && (
        <div
          data-testid="history-transfer-notice"
          role={transferNotice.kind === "failure" ? "alert" : "status"}
          className={`shrink-0 border-b border-default-200/60 px-4 py-1.5 text-xs ${
            transferNotice.kind === "failure" ? "text-danger" : "text-success"
          }`}
        >
          {transferNotice.message}
        </div>
      )}

      {/*
        Two-region layout: games-list sidebar · transcript. The sidebar
        collapses to a thin rail; both regions scroll independently (`min-h-0`
        + `overflow-y-auto`), and `min-w-0` on flex children prevents wide
        content from forcing horizontal page overflow.
      */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <aside
          data-testid="history-sidebar"
          className={`flex shrink-0 flex-col border-r border-default-200/60 bg-background transition-all duration-200 ${
            sidebarCollapsed ? "w-11 sm:w-14" : "w-60 lg:w-72"
          }`}
        >
          <HistoryGamesList
            games={games}
            gameNames={gameNames}
            selectedGameId={gameId}
            isCollapsed={sidebarCollapsed}
            isBusy={isDeleting}
            onToggleCollapsed={() => setSidebarCollapsed((c) => !c)}
            onSelect={setGameId}
            onRemove={openDelete}
          />
          {!sidebarCollapsed && gameId && events.length > 0 && (
            <HistoryNavTree
              events={events}
              selectedSeq={selectedSeq}
              onSelect={navigateToEvent}
            />
          )}
        </aside>

        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          {error ? (
            <div className="p-4 text-sm text-danger" role="alert">
              {error}
            </div>
          ) : !gameId ? (
            <div className="flex h-full items-center justify-center px-4 text-center text-sm text-default-500">
              Select a game to view its history.
            </div>
          ) : isLoading && events.length === 0 ? (
            <div className="flex h-full items-center justify-center gap-2 px-4 text-center text-sm text-default-500">
              <Spinner size="sm" />
              Loading history…
            </div>
          ) : board.reconstruction ? (
            <BoardView
              reconstruction={board.reconstruction}
              frontendUrl={frontendUrl}
              onClose={board.close}
            />
          ) : (
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              {/* Transcript usability toolbar: search + global expand/collapse. */}
              <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-default-200/60 px-4 py-2">
                <input
                  type="search"
                  data-testid="history-search"
                  aria-label="Search events"
                  placeholder="Search events…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="min-w-0 flex-1 rounded-md border border-default-200/60 bg-default-50/40 px-3 py-1.5 text-sm text-foreground outline-none transition-colors placeholder:text-default-400 focus:border-primary/60 dark:bg-white/3"
                />
                <div className="flex items-center gap-1.5">
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    data-testid="history-expand-all"
                    onPress={() =>
                      setExpandSignal((s) => ({
                        generation: s.generation + 1,
                        expanded: true,
                      }))
                    }
                  >
                    Expand all
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    data-testid="history-collapse-all"
                    onPress={() =>
                      setExpandSignal((s) => ({
                        generation: s.generation + 1,
                        expanded: false,
                      }))
                    }
                  >
                    Collapse all
                  </Button>
                </div>
              </div>
              {isTruncated && (
                <div
                  data-testid="history-truncated-notice"
                  role="status"
                  className="shrink-0 border-b border-default-200/60 px-4 py-1.5 text-xs text-warning"
                >
                  Showing the first {events.length.toLocaleString()} of{" "}
                  {(
                    selectedGame?.event_count ?? events.length
                  ).toLocaleString()}{" "}
                  recorded events for this game.
                </div>
              )}
              <HistoryTranscript
                events={events}
                selectedSeq={selectedSeq}
                onSelect={setSelectedSeq}
                onRestore={handleRestore}
                expandSignal={expandSignal}
                searchQuery={searchQuery}
                board={transcriptBoard}
                reveal={reveal}
              />
            </div>
          )}
        </main>
      </div>

      {evalOpen && gameId && (
        <RightDrawer
          ariaLabel="Evaluate game"
          testId="history-evaluate-drawer"
          onClose={() => setEvalOpen(false)}
        >
          <div className="flex shrink-0 items-center justify-between border-b border-default-200/60 px-4 py-3">
            <div className="flex flex-col">
              <span className="text-sm font-semibold text-foreground">
                Evaluate
              </span>
              <span className="text-xs text-default-400">
                Game-level — score a move, a round, a range, or the whole game.
              </span>
            </div>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              data-testid="history-evaluate-close"
              onPress={() => setEvalOpen(false)}
            >
              Close
            </Button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden">
            <EvaluationControl
              gameId={gameId}
              selectedSeq={selectedSeq}
              onEnqueued={() => {
                // Surface the new request immediately and open the queue so
                // the user can watch it without keeping this panel open.
                queue.refresh();
                setQueueOpen(true);
              }}
              judgeDraft={judgeDraft}
              onJudgeDraftChange={setJudgeDraft}
              providers={providers}
              skills={skills}
            />
          </div>
        </RightDrawer>
      )}

      {scorecardOpen && gameId && (
        <HistoryScorecard
          events={events}
          onClose={() => setScorecardOpen(false)}
        />
      )}

      {queueOpen && (
        <EvaluationQueue
          requests={queue.requests}
          gameNames={gameNames}
          isLoading={queue.isLoading}
          error={queue.error}
          onCancel={queue.cancel}
          onClear={queue.remove}
          onClearAll={queue.clearTerminal}
          onClose={() => setQueueOpen(false)}
        />
      )}

      {confirmDelete && deleteTargetId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          role="dialog"
          aria-modal="true"
          aria-label="Confirm delete history"
          data-testid="history-delete-dialog"
        >
          <div className="flex w-full max-w-sm flex-col gap-4 rounded-xl border border-default-200 bg-background p-5 shadow-2xl">
            <div className="flex flex-col gap-1">
              <h2 className="text-sm font-semibold text-foreground">
                Delete history?
              </h2>
              <p className="text-sm text-default-500">
                This permanently removes all recorded history (events and
                snapshots) for{" "}
                <span className="font-mono text-foreground">
                  {deleteTargetId}
                </span>
                . This cannot be undone.
              </p>
            </div>
            {deleteError && (
              <div
                role="alert"
                className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger"
              >
                {deleteError}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                isDisabled={isDeleting}
                data-testid="history-delete-cancel"
                onPress={() => setConfirmDelete(false)}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="danger"
                isDisabled={isDeleting}
                data-testid="history-delete-confirm"
                onPress={handleDelete}
              >
                {isDeleting ? <Spinner size="sm" /> : "Delete"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
