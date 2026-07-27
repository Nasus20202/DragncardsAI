"use client";

import { Button, Card } from "@heroui/react";
import { useState } from "react";

/**
 * A labelled, collapsible detail card used across the Play and History tabs to
 * present reasoning, tool calls/results, and other secondary event bodies. The
 * header shows a coloured status dot, a label, an optional timestamp, and an
 * expand/collapse chevron; the body (a pre-formatted block) is revealed on open.
 *
 * Presentational only — callers compute the label, dot colour, and body text.
 */
export function CollapsibleCard({
  label,
  dotClass,
  body,
  time,
  breakBody = false,
  testId,
}: {
  label: string;
  dotClass: string;
  body: string;
  /** When provided, shown to the left of the chevron in the header. */
  time?: string;
  /** Adds `break-words` to the body so long unbroken tokens wrap. */
  breakBody?: boolean;
  testId?: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Card
      variant="transparent"
      data-testid={testId}
      className="gap-0 overflow-hidden rounded-lg border border-default-200/60 bg-default-50/40 p-0 dark:bg-white/3"
    >
      <Button
        type="button"
        variant="ghost"
        fullWidth
        aria-expanded={open}
        aria-label={`${open ? "Collapse" : "Expand"} ${label}`}
        className="h-auto justify-between gap-3 rounded-none px-3 py-2 text-left hover:bg-default-100/60"
        onPress={() => setOpen((p) => !p)}
      >
        <div className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotClass}`}
          />
          <span className="text-xs font-medium text-default-500">{label}</span>
        </div>
        {time !== undefined ? (
          <div className="flex items-center gap-2 text-xs text-default-400">
            <span>{time}</span>
            <span aria-hidden="true">{open ? "▴" : "▾"}</span>
          </div>
        ) : (
          <span aria-hidden="true" className="text-xs text-default-400">
            {open ? "▴" : "▾"}
          </span>
        )}
      </Button>

      {open && (
        <div className="border-t border-default-200/60 px-3 py-2.5">
          <pre
            className={`overflow-x-auto whitespace-pre-wrap ${
              breakBody ? "break-words " : ""
            }text-xs leading-relaxed text-default-600 dark:text-default-300`}
          >
            {body}
          </pre>
        </div>
      )}
    </Card>
  );
}
