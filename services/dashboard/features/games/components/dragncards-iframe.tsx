"use client";

import { Alert } from "@heroui/react";

interface DragnCardsIframeProps {
  roomSlug: string | null;
  frontendUrl: string;
}

export function DragnCardsIframe({
  roomSlug,
  frontendUrl,
}: DragnCardsIframeProps) {
  if (!roomSlug) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-default-500">
        Select a game to view
      </div>
    );
  }

  if (!frontendUrl) {
    return (
      <div className="flex h-full items-center justify-center">
        <Alert status="danger" role="alert">
          Configuration error: DRAGNCARDS_FRONTEND_URL not set
        </Alert>
      </div>
    );
  }

  const src = `${frontendUrl}/room/${encodeURIComponent(roomSlug)}`;

  return (
    <iframe
      src={src}
      className="h-full w-full border-none"
      title="DragnCards Game Viewer"
      sandbox="allow-scripts allow-same-origin allow-forms"
    />
  );
}
