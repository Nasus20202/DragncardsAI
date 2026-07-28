"use client";

import { Button, Spinner } from "@heroui/react";
import { useRef, useState } from "react";

import {
  historyExportUrl,
  importHistoryBundle,
} from "@/features/history/lib/history-api";
import { HistoryImportResult } from "@/features/shared/lib/types";

/** What the workspace renders in its notice row after an export or import. */
export interface TransferNotice {
  kind: "success" | "failure";
  message: string;
}

function describeImport(result: HistoryImportResult): string {
  const target =
    result.game_id === result.source_game_id
      ? result.game_id
      : `${result.game_id} (exported as ${result.source_game_id})`;
  return (
    `Imported ${result.imported_events} events and ` +
    `${result.imported_snapshots} snapshots into ${target}.`
  );
}

/**
 * Export the selected game, and import a bundle into a new game. Both talk to
 * the history-service through the dashboard proxy; the import result (or the
 * service's error, which names the offending line of the file) is handed to the
 * parent so it can be shown in the history header's notice row.
 */
export function HistoryTransferControls({
  gameId,
  onNotice,
  onImported,
}: {
  gameId: string | null;
  onNotice: (notice: TransferNotice | null) => void;
  onImported: (gameId: string) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [isImporting, setIsImporting] = useState(false);

  const handleExport = () => {
    if (!gameId) return;
    onNotice(null);
    // Navigate an anchor rather than fetching: the response is an attachment
    // that can run to tens of megabytes, and the browser streams it to disk.
    const link = document.createElement("a");
    link.href = historyExportUrl(gameId);
    link.download = `dragncards-history-${gameId}.ndjson`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setIsImporting(true);
    onNotice(null);
    try {
      const result = await importHistoryBundle(file);
      onNotice({ kind: "success", message: describeImport(result) });
      onImported(result.game_id);
    } catch (e) {
      onNotice({
        kind: "failure",
        message: e instanceof Error ? e.message : "Failed to import history.",
      });
    } finally {
      setIsImporting(false);
      // Reset so re-picking the same file fires `change` again.
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  return (
    <>
      {gameId && (
        <Button
          type="button"
          size="sm"
          variant="secondary"
          data-testid="history-export"
          onPress={handleExport}
        >
          Export
        </Button>
      )}
      <Button
        type="button"
        size="sm"
        variant="secondary"
        isDisabled={isImporting}
        data-testid="history-import"
        onPress={() => fileInput.current?.click()}
      >
        {isImporting ? <Spinner size="sm" /> : "Import"}
      </Button>
      <input
        ref={fileInput}
        type="file"
        className="hidden"
        aria-label="Import history bundle"
        accept=".ndjson,.jsonl,application/x-ndjson"
        data-testid="history-import-input"
        onChange={(e) => void handleFile(e.target.files?.[0])}
      />
    </>
  );
}
