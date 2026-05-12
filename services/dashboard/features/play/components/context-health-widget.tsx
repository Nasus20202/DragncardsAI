"use client";

import { Button, Tooltip } from "@heroui/react";
import { ContextMetadata } from "@/features/shared/lib/types";

interface ContextHealthWidgetProps {
  /** Context metadata, or null while loading / session not selected. */
  contextMetadata: ContextMetadata | null;
  /** Whether a job is currently running (disables the Compact button). */
  isBusy: boolean;
  /** Called when the user clicks the Compact button. */
  onCompact: () => void;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function formatDate(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso);
  return d.toLocaleString();
}

function formatPercent(numerator: number, denominator: number): string {
  if (denominator <= 0) return "0%";
  return `${Math.round((numerator / denominator) * 100)}%`;
}

/**
 * Colour mapping:
 *  - below 70 %  → neutral (default track colour)
 *  - 70–85 %     → warning (amber)
 *  - above 85 %  → danger (red)
 */
function usageColor(ratio: number): "default" | "warning" | "danger" {
  if (ratio >= 0.85) return "danger";
  if (ratio >= 0.7) return "warning";
  return "default";
}

function usageFillClass(color: "default" | "warning" | "danger"): string {
  switch (color) {
    case "danger":
      return "bg-danger";
    case "warning":
      return "bg-warning";
    default:
      return "bg-foreground/70";
  }
}

export function ContextHealthWidget({
  contextMetadata,
  isBusy,
  onCompact,
}: ContextHealthWidgetProps) {
  if (!contextMetadata) {
    return null;
  }

  const {
    tokens_used,
    context_window_size,
    usage_ratio,
    compaction_count,
    last_compacted_at,
    multi_turn_memory,
    token_breakdown,
  } = contextMetadata;

  const memoryOff = !multi_turn_memory;
  const pct = Math.round(usage_ratio * 100);
  const color = usageColor(usage_ratio);
  const fillWidth = pct === 0 ? "0%" : `${Math.max(pct, 4)}%`;

  return (
    <div className="flex h-full flex-col gap-1 rounded-lg border border-default-200/60 bg-default-50 px-3 py-1.5 text-[11px]">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-default-700">Context</span>
        {memoryOff ? (
          <span className="rounded bg-default-200 px-1.5 py-0.5 text-default-500">
            Memory off
          </span>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            isDisabled={isBusy}
            onPress={onCompact}
            className="h-5 min-w-0 px-2 text-[11px]"
          >
            Compact
          </Button>
        )}
      </div>

      {memoryOff ? (
        <p className="text-default-500">
          Multi-turn memory is disabled for this session.
        </p>
      ) : (
        <>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-default-200/80">
            <div
              role="progressbar"
              aria-label={`Context usage ${pct}%`}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pct}
              data-value={pct}
              data-color={color}
              className={`h-full rounded-full transition-[width] duration-200 ${usageFillClass(color)}`}
              style={{ width: fillWidth }}
            />
          </div>
          <div className="flex justify-between gap-2 text-default-500">
            <Tooltip>
              <Tooltip.Trigger>
                <span className="cursor-help truncate underline decoration-dotted underline-offset-2">
                  {formatTokens(tokens_used)} /{" "}
                  {formatTokens(context_window_size)} tokens ({pct}%)
                </span>
              </Tooltip.Trigger>
              <Tooltip.Content>
                <div className="space-y-1 text-xs">
                  <div className="font-medium text-foreground">
                    Usage breakdown
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-default-500">System prompt</span>
                    <span>
                      {formatTokens(token_breakdown.system_prompt)} (
                      {formatPercent(
                        token_breakdown.system_prompt,
                        context_window_size
                      )}
                      )
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-default-500">Replay</span>
                    <span>
                      {formatTokens(token_breakdown.replay)} (
                      {formatPercent(
                        token_breakdown.replay,
                        context_window_size
                      )}
                      )
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-default-500">Tools</span>
                    <span>
                      {formatTokens(token_breakdown.tools)} (
                      {formatPercent(
                        token_breakdown.tools,
                        context_window_size
                      )}
                      )
                    </span>
                  </div>
                </div>
              </Tooltip.Content>
            </Tooltip>
            <span className="shrink-0">
              {compaction_count} compaction{compaction_count !== 1 ? "s" : ""}
            </span>
          </div>
          <div className="text-default-400">
            Last compacted: {formatDate(last_compacted_at)}
          </div>
        </>
      )}
    </div>
  );
}
