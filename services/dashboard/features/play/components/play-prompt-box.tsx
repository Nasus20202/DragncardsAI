"use client";

import { SessionDetail } from "@/features/shared/lib/types";
import { useCallback, useEffect, useRef } from "react";

export function PlayPromptBox({
  prompt,
  selectedSession,
  isBusy,
  onPromptChange,
  onSubmit,
}: {
  prompt: string;
  selectedSession: SessionDetail | null;
  isBusy: boolean;
  onPromptChange: (value: string) => void;
  onSubmit: () => void;
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
      <div className="mx-auto max-w-2xl">
        <div
          className={[
            "flex items-end gap-2 rounded-xl border px-3 py-2 transition-colors",
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

        <p className="mt-1.5 text-center text-xs text-default-400">
          Enter to send · Shift+Enter for newline
        </p>
      </div>
    </div>
  );
}
