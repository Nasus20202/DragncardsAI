"use client";

import { Button } from "@heroui/react";
import { useMemo, useState } from "react";

import { HistoryEvent } from "@/features/shared/lib/types";
import {
  buildMetaBySeq,
  buildNavTree,
  primaryEvents,
} from "@/features/history/lib/history-rounds";

/**
 * Game → rounds → moves navigation tree shown in the history sidebar under the
 * selected game. Each round node lists its moves; clicking a move selects it
 * (which also scrolls it into view in the transcript via the workspace).
 */
export function HistoryNavTree({
  events,
  selectedSeq,
  onSelect,
}: {
  events: HistoryEvent[];
  selectedSeq: number | null;
  onSelect: (seq: number) => void;
}) {
  const rounds = useMemo(() => {
    const primary = primaryEvents(events);
    const metaBySeq = buildMetaBySeq(events);
    return buildNavTree(primary, metaBySeq);
  }, [events]);

  // Collapsed rounds (by key). Rounds start expanded so moves are reachable.
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const toggleRound = (key: string) =>
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  if (rounds.length === 0) return null;

  return (
    <div
      data-testid="history-nav-tree"
      className="flex max-h-[45%] min-h-0 shrink-0 flex-col border-t border-default-200/60"
    >
      <span className="shrink-0 px-3 pt-2 text-xs font-semibold uppercase tracking-widest text-default-400">
        Navigation
      </span>
      <div className="min-h-0 flex-1 overflow-y-auto px-1 py-1">
        {rounds.map((round) => {
          const isCollapsed = collapsed.has(round.key);
          return (
            <div key={round.key} className="flex flex-col">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                data-testid={`history-nav-round-${round.key}`}
                aria-expanded={!isCollapsed}
                onPress={() => toggleRound(round.key)}
                className="flex h-auto justify-start gap-1.5 rounded bg-transparent px-2 py-1 text-left text-xs font-semibold text-default-600 transition-colors hover:bg-default-100 hover:text-foreground"
              >
                <span aria-hidden="true" className="text-default-400">
                  {isCollapsed ? "▸" : "▾"}
                </span>
                {round.label}
                <span className="font-normal text-default-400">
                  ({round.moves.length})
                </span>
              </Button>
              {!isCollapsed && (
                <ul className="flex flex-col">
                  {round.moves.map((move) => {
                    const active = selectedSeq === move.seq;
                    return (
                      <li key={move.seq}>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          data-testid={`history-nav-move-${move.seq}`}
                          aria-current={active ? "true" : undefined}
                          onPress={() => onSelect(move.seq)}
                          className={[
                            "flex h-auto w-full items-center justify-start truncate rounded bg-transparent py-1 pl-7 pr-2 text-left text-xs transition-colors",
                            active
                              ? "bg-primary/10 text-foreground"
                              : "text-default-500 hover:bg-default-100/60 hover:text-foreground",
                          ].join(" ")}
                        >
                          {/* Hero UI's Button props do not accept `title`;
                              the tooltip lives on the label text instead. */}
                          <span className="truncate" title={move.label}>
                            {move.label}
                          </span>
                        </Button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
