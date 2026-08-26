"use client";

import {
  Button,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalHeading,
  Radio,
  RadioGroup,
  Spinner,
} from "@heroui/react";
import { useRef, useState } from "react";

import {
  historyExportFilename,
  historyExportUrl,
  importHistoryBundle,
} from "@/features/history/lib/history-api";
import { TextInputField } from "@/features/shared/components/form-fields";
import {
  GamePlatform,
  HistoryExportMode,
  HistoryImportResult,
} from "@/features/shared/lib/types";
import { HistoryGameRef } from "@/features/history/lib/history-game-ref";

/** What the workspace renders in its notice row after an export or import. */
export interface TransferNotice {
  kind: "success" | "failure";
  message: string;
}

const EXPORT_MODES: readonly HistoryExportMode[] = ["full", "minimal"];

const EXPORT_MODE_LABEL: Record<HistoryExportMode, string> = {
  full: "Full",
  minimal: "Minimal",
};

const EXPORT_MODE_DESCRIPTION: Record<HistoryExportMode, string> = {
  full: "Lossless: every recorded move with the prompt material behind it.",
  minimal:
    "Leaves out an agent move's conversation context — the prompt material the model was sent — and nothing else.",
};

/**
 * Where an import puts the history it reads. The three are one question, not
 * two, because the service refuses a request that both names a target and asks
 * for a new one.
 */
type ImportTarget = "new" | "bundle" | "custom";

const IMPORT_TARGETS: readonly ImportTarget[] = ["new", "bundle", "custom"];

const IMPORT_TARGET_LABEL: Record<ImportTarget, string> = {
  new: "A new game id",
  bundle: "The id the bundle came from",
  custom: "An id I choose",
};

const IMPORT_TARGET_DESCRIPTION: Record<ImportTarget, string> = {
  new: "The service mints one. The only target that cannot collide with a game that already has history.",
  bundle:
    "Refused if that game still has recorded history, so re-importing over a game means deleting its history first.",
  custom: "Refused if the id you name already has recorded history.",
};

/** How a bundle's declared mode reads in the notice row. */
const IMPORT_MODE_NOTE: Record<HistoryExportMode, string> = {
  full: "a full bundle",
  minimal: "a minimal bundle, which carries no agent prompt material",
};

function describeImport(result: HistoryImportResult): string {
  const target =
    result.game_id === result.source_game_id
      ? result.game_id
      : `${result.game_id} (exported as ${result.source_game_id})`;
  const written =
    `Imported ${result.imported_events} events and ` +
    `${result.imported_snapshots} snapshots into ${target} from ` +
    `${IMPORT_MODE_NOTE[result.mode]}.`;
  // Payloads are stored exactly as they were recorded, so a bundle that landed
  // on another id still names the game it came from inside conversations and
  // tool arguments. Saying how many events that is turns something a reader
  // would otherwise hit mid-transcript into a fact the import itself declared.
  if (
    result.game_id !== result.source_game_id &&
    result.source_id_references > 0
  ) {
    return (
      `${written} ${result.source_id_references} imported events still name ` +
      `${result.source_game_id} inside their payloads.`
    );
  }
  return written;
}

/**
 * Export the selected game, and import a bundle into a game. Both talk to the
 * history-service through the dashboard proxy; the import result (or the
 * service's error, which names the offending line of the file) is handed to the
 * parent so it can be shown in the history header's notice row.
 *
 * Each side asks its one question in a dialog rather than acting on the press:
 * an export that always shipped the prompt material had no way to produce the
 * shareable bundle, and an import that always used the bundle's own id 409'd on
 * the common case of importing a game you already have.
 */
export function HistoryTransferControls({
  gameId,
  platform = "dragncards",
  onNotice,
  onImported,
}: {
  gameId: string | null;
  platform?: GamePlatform;
  onNotice: (notice: TransferNotice | null) => void;
  onImported: (game: HistoryGameRef) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [exportMode, setExportMode] = useState<HistoryExportMode>("full");
  const [isExportOpen, setIsExportOpen] = useState(false);
  // The picked file is what opens the import dialog: there is nothing to choose
  // a target for until one has been read off the input.
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  // Defaults to the target that cannot 409, so the common case — reading someone
  // else's bundle, or a second copy of a game already held — just works.
  const [importTarget, setImportTarget] = useState<ImportTarget>("new");
  const [customGameId, setCustomGameId] = useState("");
  const [isImporting, setIsImporting] = useState(false);

  const handleExport = () => {
    if (!gameId) return;
    onNotice(null);
    setIsExportOpen(false);
    // Navigate an anchor rather than fetching: the response is an attachment
    // that can run to tens of megabytes, and the browser streams it to disk.
    const link = document.createElement("a");
    link.href = historyExportUrl(gameId, exportMode, platform);
    link.download = historyExportFilename(gameId, exportMode);
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const handleFile = (file: File | undefined) => {
    // Reset the input as soon as the file is held so re-picking the same file
    // fires `change` again — the dialog it opens can be dismissed.
    if (fileInput.current) fileInput.current.value = "";
    if (!file) return;
    onNotice(null);
    setPendingFile(file);
  };

  const closeImport = () => {
    setPendingFile(null);
    setCustomGameId("");
  };

  const handleImport = async () => {
    if (!pendingFile) return;
    setIsImporting(true);
    onNotice(null);
    try {
      const result = await importHistoryBundle(pendingFile, {
        asNew: importTarget === "new",
        gameId: importTarget === "custom" ? customGameId.trim() : undefined,
      });
      onNotice({ kind: "success", message: describeImport(result) });
      onImported({ gameId: result.game_id, platform: result.platform });
      closeImport();
    } catch (e) {
      onNotice({
        kind: "failure",
        message: e instanceof Error ? e.message : "Failed to import history.",
      });
      // The dialog stays open on failure: a 409 on the bundle's own id is
      // answered by picking another target, not by picking the file again.
    } finally {
      setIsImporting(false);
    }
  };

  const importDisabled =
    isImporting || (importTarget === "custom" && customGameId.trim() === "");

  return (
    <>
      {gameId && (
        <Button
          type="button"
          size="sm"
          variant="secondary"
          data-testid="history-export"
          onPress={() => {
            onNotice(null);
            setIsExportOpen(true);
          }}
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
        onChange={(e) => handleFile(e.target.files?.[0])}
      />

      <Modal
        isOpen={isExportOpen && gameId !== null}
        onOpenChange={setIsExportOpen}
      >
        <Modal.Backdrop variant="blur">
          <Modal.Container size="sm" placement="center">
            <Modal.Dialog aria-label="Choose what to export">
              <ModalHeader className="pb-2">
                <ModalHeading className="text-base font-semibold">
                  Export history
                </ModalHeading>
              </ModalHeader>
              <ModalBody className="grid gap-3">
                <p className="text-sm text-default-500">
                  Downloads {gameId} as an NDJSON bundle. Pick how much of it to
                  carry.
                </p>
                <RadioGroup
                  aria-label="Export mode"
                  value={exportMode}
                  onChange={(next) => setExportMode(next as HistoryExportMode)}
                  className="gap-2"
                >
                  {EXPORT_MODES.map((mode) => (
                    <Radio
                      key={mode}
                      value={mode}
                      aria-label={EXPORT_MODE_LABEL[mode]}
                    >
                      {/* Radio.Content is the clickable RadioButton, so the test
                          id and the click target belong on it. */}
                      <Radio.Content
                        className="flex items-start gap-2"
                        data-testid={`history-export-mode-${mode}`}
                      >
                        <Radio.Control className="mt-0.5 shrink-0">
                          <Radio.Indicator />
                        </Radio.Control>
                        <span className="flex flex-col">
                          <span className="text-sm text-foreground">
                            {EXPORT_MODE_LABEL[mode]}
                          </span>
                          <span className="text-xs text-default-400">
                            {EXPORT_MODE_DESCRIPTION[mode]}
                          </span>
                        </span>
                      </Radio.Content>
                    </Radio>
                  ))}
                </RadioGroup>
              </ModalBody>
              <ModalFooter className="pt-4">
                <Button
                  variant="ghost"
                  data-testid="history-export-cancel"
                  onPress={() => setIsExportOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  data-testid="history-export-confirm"
                  onPress={handleExport}
                >
                  Download
                </Button>
              </ModalFooter>
            </Modal.Dialog>
          </Modal.Container>
        </Modal.Backdrop>
      </Modal>

      <Modal
        isOpen={pendingFile !== null}
        onOpenChange={(isOpen) => {
          if (!isOpen) closeImport();
        }}
      >
        <Modal.Backdrop variant="blur">
          <Modal.Container size="sm" placement="center">
            <Modal.Dialog aria-label="Choose where to import">
              <ModalHeader className="pb-2">
                <ModalHeading className="text-base font-semibold">
                  Import history
                </ModalHeading>
              </ModalHeader>
              <ModalBody className="grid gap-3">
                <p className="text-sm text-default-500">
                  Reading{" "}
                  <span
                    className="font-medium text-foreground"
                    data-testid="history-import-filename"
                  >
                    {pendingFile?.name}
                  </span>
                  . Pick the game it should land under.
                </p>
                <RadioGroup
                  aria-label="Import target"
                  value={importTarget}
                  isDisabled={isImporting}
                  onChange={(next) => setImportTarget(next as ImportTarget)}
                  className="gap-2"
                >
                  {IMPORT_TARGETS.map((target) => (
                    <Radio
                      key={target}
                      value={target}
                      aria-label={IMPORT_TARGET_LABEL[target]}
                    >
                      <Radio.Content
                        className="flex items-start gap-2"
                        data-testid={`history-import-target-${target}`}
                      >
                        <Radio.Control className="mt-0.5 shrink-0">
                          <Radio.Indicator />
                        </Radio.Control>
                        <span className="flex flex-col">
                          <span className="text-sm text-foreground">
                            {IMPORT_TARGET_LABEL[target]}
                          </span>
                          <span className="text-xs text-default-400">
                            {IMPORT_TARGET_DESCRIPTION[target]}
                          </span>
                        </span>
                      </Radio.Content>
                    </Radio>
                  ))}
                </RadioGroup>
                {importTarget === "custom" && (
                  <div className="pl-6">
                    <TextInputField
                      id="history-import-game-id-field"
                      label="Target game id"
                      placeholder="e.g. demo-001"
                      value={customGameId}
                      disabled={isImporting}
                      inputTestId="history-import-game-id"
                      onChange={setCustomGameId}
                    />
                  </div>
                )}
              </ModalBody>
              <ModalFooter className="pt-4">
                <Button
                  variant="ghost"
                  data-testid="history-import-cancel"
                  isDisabled={isImporting}
                  onPress={closeImport}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  data-testid="history-import-confirm"
                  isDisabled={importDisabled}
                  onPress={() => void handleImport()}
                >
                  {isImporting ? <Spinner size="sm" /> : "Import"}
                </Button>
              </ModalFooter>
            </Modal.Dialog>
          </Modal.Container>
        </Modal.Backdrop>
      </Modal>
    </>
  );
}
