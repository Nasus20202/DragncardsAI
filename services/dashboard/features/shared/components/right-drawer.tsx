"use client";

import { Drawer } from "@heroui/react";
import { ReactNode } from "react";

/**
 * A right-anchored slide-over panel shell used by the History tab for the
 * Evaluate, evaluations queue, and player scorecard drawers. Renders a dimmed
 * backdrop that closes on outside click and a full-height dialog on the right
 * edge. Header and body content are supplied as children so each drawer keeps
 * its own layout.
 *
 * Callers mount this conditionally, so the drawer is always open while rendered
 * and reports dismissal through `onClose`.
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
    <Drawer
      isOpen
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Drawer.Backdrop>
        <Drawer.Content placement="right">
          <Drawer.Dialog
            aria-label={ariaLabel}
            data-testid={testId}
            className={`flex h-full w-full ${maxWidthClass} flex-col overflow-hidden border-l border-default-200 bg-background p-0 shadow-2xl`}
          >
            {children}
          </Drawer.Dialog>
        </Drawer.Content>
      </Drawer.Backdrop>
    </Drawer>
  );
}
