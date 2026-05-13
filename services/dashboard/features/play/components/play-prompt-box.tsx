"use client";

import { ContextMetadata, SessionDetail } from "@/features/shared/lib/types";
import { ContextHealthWidget } from "@/features/play/components/context-health-widget";
import { useCallback, useEffect, useRef } from "react";

export function PlayPromptBox({
  prompt,
  selectedSession,
  activeJobId,
  isBusy,
  cancelPending,
  contextMetadata,
  onPromptChange,
  onSubmit,
  onCancelExecution,
  onCompact,
}: {
  prompt: string;
  selectedSession: SessionDetail | null;
  activeJobId: string | null;
  isBusy: boolean;
  cancelPending: boolean;
  contextMetadata: ContextMetadata | null;
  onPromptChange: (value: string) => void;
  onSubmit: () => void;
  onCancelExecution: () => void;
  onCompact: () => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const disabled = !selectedSession || selectedSession.status !== "active";
  const canSend = Boolean(prompt.trim()) && !isBusy && !disabled;
  const showCancel = activeJobId !== null;

  /* Auto-resize */
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [prompt]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (canSend) onSubmit();
      }
    },
    [canSend, onSubmit]
  );

  return (
    <div className="shrink-0 border-t border-default-200/60 bg-background px-2 py-3 sm:px-4">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-stretch lg:gap-3">
        <div className="min-w-0 w-full flex-1 lg:flex">
          <div
            className={[
              "flex w-full flex-col gap-2 rounded-xl border px-2.5 py-3 transition-colors sm:flex-row sm:items-end sm:px-3 sm:py-2 lg:h-full",
              "bg-default-50 dark:bg-white/3",
              disabled
                ? "border-default-200 opacity-60"
                : "border-default-300 focus-within:border-default-400",
            ].join(" ")}
          >
            <textarea
              data-testid="play-prompt-input"
              ref={ref}
              aria-label="Message"
              rows={1}
              value={prompt}
              disabled={disabled}
              placeholder={
                disabled
                  ? "Select an active session to start."
                  : "Message the agent..."
              }
              className="min-h-24 w-full flex-1 resize-none bg-transparent py-1 text-[17px] leading-6 text-foreground placeholder-default-400 outline-none sm:min-h-11 sm:py-0 sm:text-base sm:leading-normal"
              onChange={(e) => onPromptChange(e.target.value)}
              onKeyDown={handleKeyDown}
            />

            <div className="flex shrink-0 gap-2 sm:mb-0.5">
              {showCancel ? (
                <button
                  type="button"
                  aria-label="Cancel active execution"
                  disabled={cancelPending}
                  className={[
                    "rounded-lg px-3 py-2 text-sm font-semibold transition-colors sm:px-3 sm:py-1.5",
                    cancelPending
                      ? "cursor-not-allowed bg-default-200 text-default-400"
                      : "bg-danger/12 text-danger hover:bg-danger/18",
                  ].join(" ")}
                  onClick={onCancelExecution}
                >
                  {cancelPending ? "Cancelling..." : "Cancel"}
                </button>
              ) : null}
              <button
                data-testid="play-prompt-send"
                type="button"
                aria-label="Send message"
                disabled={!canSend}
                className={[
                  "rounded-lg px-3 py-2 text-sm font-semibold transition-colors sm:px-3 sm:py-1.5",
                  canSend
                    ? "bg-foreground text-background hover:opacity-80"
                    : "cursor-not-allowed bg-default-200 text-default-400",
                ].join(" ")}
                onClick={onSubmit}
              >
                {isBusy ? "…" : "Send"}
              </button>
            </div>
          </div>
        </div>

        <div className="w-full lg:flex lg:w-56 lg:shrink-0">
          {contextMetadata && (
            <ContextHealthWidget
              contextMetadata={contextMetadata}
              isBusy={isBusy}
              onCompact={onCompact}
            />
          )}
        </div>
      </div>
    </div>
  );
}
