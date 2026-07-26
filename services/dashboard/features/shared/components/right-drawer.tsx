"use client";

import { ReactNode } from "react";

/**
 * A right-anchored slide-over panel shell used by the History tab for the
 * Evaluate, evaluations queue, and player scorecard drawers. Renders a dimmed
 * backdrop that closes on outside click and a full-height `aside` dialog on the
 * right edge. Header and body content are supplied as children so each drawer
 * keeps its own layout.
 */
export function RightDrawer({
  ariaLabel,
  onClose,
  testId,
  maxWidthClass = "max-w-md",
  children,
}: {
  ariaLabel: string;
  onClose: () => void;
  testId?: string;
  /** Tailwind max-width class for the panel (e.g. `max-w-md`, `max-w-lg`). */
  maxWidthClass?: string;
  children: ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/40"
      data-testid={testId}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel}
        className={`flex h-full w-full ${maxWidthClass} flex-col overflow-hidden border-l border-default-200 bg-background shadow-2xl`}
      >
        {children}
      </aside>
    </div>
  );
}
