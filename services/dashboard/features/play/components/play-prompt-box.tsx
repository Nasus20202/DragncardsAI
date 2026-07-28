"use client";

import { Chip } from "@heroui/react";
import {
  ContextMetadata,
  SessionDetail,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";
import { ContextHealthWidget } from "@/features/play/components/context-health-widget";
import {
  filterMentionableSkills,
  findSkillMention,
  removeSkillMention,
  SkillMention,
} from "@/features/play/lib/skill-mentions";
import {
  SkillMentionPicker,
  skillMentionOptionId,
} from "@/features/play/components/skill-mention-picker";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const MENTION_PICKER_ID = "play-skill-mention-picker";

export function PlayPromptBox({
  prompt,
  selectedSession,
  activeJobId,
  isBusy,
  cancelPending,
  contextMetadata,
  skills,
  attachedSkills,
  onPromptChange,
  onSubmit,
  onCancelExecution,
  onCompact,
  onAttachSkill,
  onDetachSkill,
}: {
  prompt: string;
  selectedSession: SessionDetail | null;
  activeJobId: string | null;
  isBusy: boolean;
  cancelPending: boolean;
  contextMetadata: ContextMetadata | null;
  /** Skills the session could use, as offered by the mention picker. */
  skills: SkillDefinitionResponse[];
  /** Skills currently assigned to the session; the same set the settings panel toggles. */
  attachedSkills: string[];
  onPromptChange: (value: string) => void;
  onSubmit: () => void;
  onCancelExecution: () => void;
  onCompact: () => void;
  onAttachSkill: (skillName: string) => void;
  onDetachSkill: (skillName: string) => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const pendingCaretRef = useRef<number | null>(null);
  const [mention, setMention] = useState<SkillMention | null>(null);
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const disabled = !selectedSession || selectedSession.status !== "active";
  const canSend = Boolean(prompt.trim()) && !isBusy && !disabled;
  const showCancel = activeJobId !== null;

  const mentionOptions = useMemo(
    () =>
      mention
        ? filterMentionableSkills(skills, mention.query, attachedSkills)
        : [],
    [attachedSkills, mention, skills]
  );
  const isPickerOpen = mention !== null && mentionOptions.length > 0;
  const highlighted = Math.min(highlightedIndex, mentionOptions.length - 1);

  /* Auto-resize */
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;

    // Removing a mention token moves the caret; restore it once the owner has
    // handed back the shortened text, so typing continues where it left off.
    const caret = pendingCaretRef.current;
    if (caret !== null) {
      pendingCaretRef.current = null;
      el.focus();
      el.setSelectionRange(caret, caret);
    }
  }, [prompt]);

  const handleChange = useCallback(
    (event: React.ChangeEvent<HTMLTextAreaElement>) => {
      const { value, selectionStart } = event.target;
      onPromptChange(value);
      // Only an active session can be assigned a skill, so only then is a
      // mention worth tracking.
      setMention(
        disabled
          ? null
          : findSkillMention(value, selectionStart ?? value.length)
      );
      setHighlightedIndex(0);
    },
    [disabled, onPromptChange]
  );

  const attachMentionedSkill = useCallback(
    (skillName: string) => {
      if (!mention) return;
      const next = removeSkillMention(prompt, mention);
      pendingCaretRef.current = next.caret;
      setMention(null);
      setHighlightedIndex(0);
      onPromptChange(next.text);
      onAttachSkill(skillName);
    },
    [mention, onAttachSkill, onPromptChange, prompt]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (isPickerOpen) {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          const step = e.key === "ArrowDown" ? 1 : -1;
          const count = mentionOptions.length;
          setHighlightedIndex((current) => (current + step + count) % count);
          return;
        }
        if (e.key === "Enter" || e.key === "Tab") {
          e.preventDefault();
          attachMentionedSkill(mentionOptions[highlighted].name);
          return;
        }
        if (e.key === "Escape") {
          e.preventDefault();
          setMention(null);
          return;
        }
      }
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (canSend) onSubmit();
      }
    },
    [
      attachMentionedSkill,
      canSend,
      highlighted,
      isPickerOpen,
      mentionOptions,
      onSubmit,
    ]
  );

  return (
    <div className="relative shrink-0 border-t border-default-200/60 bg-background px-2 py-3 sm:px-4">
      {isPickerOpen && (
        <SkillMentionPicker
          id={MENTION_PICKER_ID}
          skills={mentionOptions}
          highlightedIndex={highlighted}
          onSelect={attachMentionedSkill}
        />
      )}

      {attachedSkills.length > 0 && (
        <div
          className="mb-2 flex flex-wrap items-center gap-1.5"
          data-testid="composer-skill-chips"
        >
          {attachedSkills.map((skillName) => (
            <Chip color="accent" key={skillName} size="sm" variant="soft">
              <span className="flex items-center gap-1">
                {skillName}
                <button
                  aria-label={`Detach skill ${skillName}`}
                  className="text-default-400 hover:text-default-600 disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={disabled}
                  type="button"
                  onClick={() => onDetachSkill(skillName)}
                >
                  <span aria-hidden="true">✕</span>
                </button>
              </span>
            </Chip>
          ))}
        </div>
      )}

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
              aria-activedescendant={
                isPickerOpen
                  ? skillMentionOptionId(
                      MENTION_PICKER_ID,
                      mentionOptions[highlighted].name
                    )
                  : undefined
              }
              aria-controls={isPickerOpen ? MENTION_PICKER_ID : undefined}
              rows={1}
              value={prompt}
              disabled={disabled}
              placeholder={
                disabled
                  ? "Select an active session to start."
                  : "Message the agent..."
              }
              className="min-h-24 w-full flex-1 resize-none bg-transparent py-1 text-[17px] leading-6 text-foreground placeholder-default-400 outline-none sm:min-h-11 sm:py-0 sm:text-base sm:leading-normal"
              onChange={handleChange}
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
