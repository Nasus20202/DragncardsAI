"use client";

import { ContextMetadata, SessionDetail } from "@/features/shared/lib/types";
import { ContextHealthWidget } from "@/features/play/components/context-health-widget";
import { useCallback, useEffect, useRef } from "react";

export function PlayPromptBox({
  prompt,
  selectedSession,
  isBusy,
  contextMetadata,
  onPromptChange,
  onSubmit,
  onCompact,
}: {
  prompt: string;
  selectedSession: SessionDetail | null;
  isBusy: boolean;
  contextMetadata: ContextMetadata | null;
  onPromptChange: (value: string) => void;
  onSubmit: () => void;
  onCompact: () => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const disabled = !selectedSession || selectedSession.status !== "active";
  const canSend = Boolean(prompt.trim()) && !isBusy && !disabled;

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
    [canSend, onSubmit],
  );

  return (
    <div className="shrink-0 border-t border-default-200/60 bg-background px-4 py-3">
      <div className="flex items-start gap-3">
        {/* Spacer left — mirrors the context widget width so input stays centered */}
        <div className="w-64 shrink-0" />

        {/* Input centered */}
        <div className="min-w-0 flex-1">
          <div
            className={[
              "mx-auto flex max-w-3xl items-end gap-2 rounded-xl border px-3 py-2 transition-colors",
              "bg-default-50 dark:bg-white/3",
              disabled
                ? "border-default-200 opacity-60"
                : "border-default-300 focus-within:border-default-400",
            ].join(" ")}
          >
            <textarea
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
              className="min-h-9 flex-1 resize-none bg-transparent text-base text-foreground placeholder-default-400 outline-none"
              onChange={(e) => onPromptChange(e.target.value)}
              onKeyDown={handleKeyDown}
            />

            <button
              type="button"
              aria-label="Send message"
              disabled={!canSend}
              className={[
                "mb-0.5 shrink-0 rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors",
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

        {/* Context widget — right, bottom-aligned with input */}
        <div className="w-64 shrink-0 self-end">
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
