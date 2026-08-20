"use client";

import { GameSession } from "@/features/shared/lib/types";
import {
  resolveGameViewerUrl,
  viewerConfigurationMessage,
  ViewerUrls,
} from "@/features/games/lib/viewer-resolver";

interface DragnCardsIframeProps {
  game?: GameSession | null;
  urls: ViewerUrls;
}

export function DragnCardsIframe({
  game,
  urls,
}: DragnCardsIframeProps) {
  const src = resolveGameViewerUrl(game, urls);
  if (!src) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center text-sm text-default-500">
        {viewerConfigurationMessage(game, urls)}
      </div>
    );
  }

  return (
    <iframe
      src={src}
      className="h-full w-full border-none"
      title={`${game?.platform === "marvel-lcg" ? "Marvel LCG" : "DragnCards"} Game Viewer`}
      sandbox="allow-scripts allow-same-origin allow-forms"
    />
  );
}
