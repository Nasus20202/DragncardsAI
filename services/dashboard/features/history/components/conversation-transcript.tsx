"use client";

import {
  TranscriptItem,
  mapConversationToTranscript,
} from "@/features/history/lib/conversation-transcript";
import { CollapsibleCard } from "@/features/shared/components/collapsible-card";
import { JsonValue } from "@/features/shared/lib/types";

/**
 * Renders an agent move's captured conversation as a readable transcript using
 * the same visual language as the Play tab (message bubbles, collapsible
 * reasoning/tool cards). Presentational only — no scroll-lock, prompt box, or
 * job streaming; it consumes a mapped, static message array.
 */

function TranscriptRow({ item }: { item: TranscriptItem }) {
  switch (item.kind) {
    case "system":
      return (
        <CollapsibleCard
          label="System prompt"
          dotClass="bg-secondary"
          body={item.text}
          breakBody
          testId="transcript-system"
        />
      );
    case "user":
      return (
        <div className="flex justify-end" data-testid="transcript-user">
          <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-tr-sm bg-default-100 px-4 py-2.5 text-sm leading-relaxed text-foreground dark:bg-white/6">
            {item.text}
          </div>
        </div>
      );
    case "assistant":
      return (
        <p
          data-testid="transcript-assistant"
          className="whitespace-pre-wrap break-words text-sm leading-relaxed text-foreground"
        >
          {item.text}
        </p>
      );
    case "tool_call":
      return (
        <CollapsibleCard
          label={`Tool call: ${item.call.name}`}
          dotClass="bg-default-400"
          body={item.call.arguments || "(no arguments)"}
          breakBody
          testId="transcript-tool-call"
        />
      );
    case "tool_result":
      return (
        <CollapsibleCard
          label={`Tool result${item.name ? `: ${item.name}` : ""}`}
          dotClass="bg-default-300"
          body={item.text || "(empty result)"}
          breakBody
          testId="transcript-tool-result"
        />
      );
  }
}

export function ConversationTranscript({
  context,
}: {
  context: JsonValue | undefined | null;
}) {
  const items = mapConversationToTranscript(context);

  if (items.length === 0) {
    return (
      <p data-testid="transcript-empty" className="text-xs text-default-400">
        No conversation captured for this move.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2" data-testid="conversation-transcript">
      {items.map((item, i) => (
        <TranscriptRow key={i} item={item} />
      ))}
    </div>
  );
}
