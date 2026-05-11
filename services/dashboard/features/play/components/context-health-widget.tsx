"use client";

import { Button, ProgressBar, Tooltip } from "@heroui/react";
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

export function ContextHealthWidget({
  contextMetadata,
  isBusy,
  onCompact,
}: ContextHealthWidgetProps) {
  if (!contextMetadata) {
    return null;
  }

  const { tokens_used, context_window_size, usage_ratio, compaction_count, last_compacted_at, multi_turn_memory } =
    contextMetadata;

  const memoryOff = !multi_turn_memory;
  const pct = Math.round(usage_ratio * 100);
  const color = usageColor(usage_ratio);

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-default-200/60 bg-default-50 px-3 py-2 text-xs">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-default-700">Context</span>
        {memoryOff ? (
          <span className="rounded bg-default-200 px-1.5 py-0.5 text-default-500">Memory off</span>
        ) : (
          <Tooltip content="Summarise conversation history to free context space">
            <Button
              size="sm"
              variant="flat"
              isDisabled={isBusy}
              onPress={onCompact}
              className="h-6 min-w-0 px-2 text-xs"
            >
              Compact
            </Button>
          </Tooltip>
        )}
      </div>

      {memoryOff ? (
        <p className="text-default-500">Multi-turn memory is disabled for this session.</p>
      ) : (
        <>
          <ProgressBar
            aria-label={`Context usage ${pct}%`}
            value={pct}
            color={color}
            className="w-full"
          />
          <div className="flex justify-between text-default-500">
            <span>
              {formatTokens(tokens_used)} / {formatTokens(context_window_size)} tokens ({pct}%)
            </span>
            <span>
              {compaction_count} compaction{compaction_count !== 1 ? "s" : ""}
            </span>
          </div>
          <div className="text-default-400">Last compacted: {formatDate(last_compacted_at)}</div>
        </>
      )}
    </div>
  );
}
