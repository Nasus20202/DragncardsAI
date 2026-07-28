"use client";

import {
  Button,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalHeading,
} from "@heroui/react";

/**
 * Confirmation dialog for the destructive session-removal control in the Play
 * session list. Naming the session in the body keeps a mis-aimed click on the
 * hover-revealed ✕ from silently deleting the wrong session. Deletion happens
 * only when the danger action is pressed; dismissing the dialog cancels.
 *
 * The wording tracks what the orchestrator's `DELETE /sessions/{id}` actually
 * does — cancel in-flight work, then remove the session with its configuration
 * and transcript — rather than the terminate-only behaviour this control had
 * before.
 */
export function RemoveSessionModal({
  sessionName,
  isBusy = false,
  onCancel,
  onConfirm,
}: {
  sessionName: string;
  isBusy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Modal
      isOpen
      onOpenChange={(isOpen) => {
        if (!isOpen) onCancel();
      }}
    >
      <Modal.Backdrop variant="blur">
        <Modal.Container size="sm" placement="center">
          <Modal.Dialog aria-label="Confirm session removal">
            <ModalHeader className="pb-2">
              <ModalHeading className="text-base font-semibold">
                Delete session?
              </ModalHeading>
            </ModalHeader>
            <ModalBody>
              <p className="text-sm text-default-500">
                This permanently deletes{" "}
                <span
                  className="font-medium text-foreground"
                  data-testid="remove-session-name"
                >
                  {sessionName}
                </span>{" "}
                with its settings and full transcript. Any running work is
                cancelled first. This cannot be undone.
              </p>
            </ModalBody>
            <ModalFooter className="pt-4">
              <Button
                variant="ghost"
                data-testid="remove-session-cancel"
                isDisabled={isBusy}
                onPress={onCancel}
              >
                Cancel
              </Button>
              <Button
                variant="danger"
                data-testid="remove-session-confirm"
                isDisabled={isBusy}
                onPress={onConfirm}
              >
                Delete
              </Button>
            </ModalFooter>
          </Modal.Dialog>
        </Modal.Container>
      </Modal.Backdrop>
    </Modal>
  );
}
