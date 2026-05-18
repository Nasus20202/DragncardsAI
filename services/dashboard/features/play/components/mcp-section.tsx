"use client";

import {
  Button,
  Input,
  ListBox,
  ListBoxItem,
  Modal,
  ModalBody,
  ModalCloseTrigger,
  ModalFooter,
  ModalHeader,
  ModalHeading,
  Select,
  TextField,
} from "@heroui/react";
import { useState } from "react";
import type {
  McpAssignmentResponse,
  McpRegistryResponse,
} from "@/features/shared/lib/types";
import { ToggleInfoRow } from "@/features/play/components/toggle-info-row";

const SUPPORTED_TRANSPORTS = [
  { value: "streamable-http", label: "Streamable HTTP" },
  { value: "sse", label: "SSE" },
] as const;

type TransportType = (typeof SUPPORTED_TRANSPORTS)[number]["value"];

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-default-400">
      {children}
    </p>
  );
}

function McpCard({
  mcp,
  isBusy,
  onToggle,
  onDelete,
}: {
  mcp: McpAssignmentResponse;
  isBusy: boolean;
  onToggle: (mcpName: string, enabled: boolean) => Promise<void>;
  onDelete?: (mcpName: string) => Promise<void>;
}) {
  const headerStr = mcp.headers
    ? Object.entries(mcp.headers)
        .map(([k, v]) => `${k}: ${v}`)
        .join(", ")
    : null;

  return (
    <ToggleInfoRow
      label={mcp.name}
      description={mcp.custom ? "Custom MCP" : undefined}
      checked={mcp.enabled}
      disabled={isBusy}
      onChange={(checked) => onToggle(mcp.name, checked)}
      infoLabel={`Info about ${mcp.name}`}
      infoContent={
        <div className="space-y-1 p-1">
          <p className="text-xs text-foreground/90">{mcp.transport}</p>
          <p className="break-all text-[11px] text-default-500">
            {mcp.server_url}
          </p>
          {headerStr && (
            <p className="break-all text-[11px] text-default-500">
              Headers: {headerStr}
            </p>
          )}
        </div>
      }
      action={
        mcp.custom && onDelete
          ? {
              label: "Delete",
              ariaLabel: `Delete ${mcp.name}`,
              disabled: isBusy,
              onPress: () => onDelete(mcp.name),
              variant: "danger-soft",
            }
          : undefined
      }
      actionVisibility={mcp.custom ? "hover" : "always"}
    />
  );
}

function KeyValuePairEditor({
  pairs,
  onChange,
}: {
  pairs: { key: string; value: string }[];
  onChange: (pairs: { key: string; value: string }[]) => void;
}) {
  const addPair = () => onChange([...pairs, { key: "", value: "" }]);
  const removePair = (index: number) =>
    onChange(pairs.filter((_, i) => i !== index));
  const updatePair = (index: number, field: "key" | "value", text: string) => {
    const newPairs = [...pairs];
    newPairs[index][field] = text;
    onChange(newPairs);
  };

  return (
    <div className="grid gap-2">
      {pairs.map((pair, index) => (
        <div key={index} className="flex gap-2">
          <Input
            aria-label={`Header key ${index + 1}`}
            placeholder="Key"
            value={pair.key}
            onChange={(e) => updatePair(index, "key", e.target.value)}
          />
          <Input
            aria-label={`Header value ${index + 1}`}
            placeholder="Value"
            value={pair.value}
            onChange={(e) => updatePair(index, "value", e.target.value)}
          />
          <Button
            aria-label={`Remove header ${index + 1}`}
            isIconOnly
            variant="ghost"
            onPress={() => removePair(index)}
          >
            <span aria-hidden="true">−</span>
          </Button>
        </div>
      ))}
      <Button
        aria-label="Add header"
        variant="ghost"
        onPress={addPair}
        className="justify-start"
      >
        <span aria-hidden="true">+</span> Add Header
      </Button>
    </div>
  );
}

export function McpSection({
  mcps,
  isBusy,
  onToggle,
  onAdd,
  onDelete,
}: {
  mcps: McpAssignmentResponse[];
  isBusy: boolean;
  onToggle: (mcpName: string, enabled: boolean) => Promise<void>;
  onAdd: (mcp: McpRegistryResponse) => Promise<void>;
  onDelete?: (mcpName: string) => Promise<void>;
}) {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [name, setName] = useState("");
  const [transport, setTransport] = useState<TransportType>("streamable-http");
  const [serverUrl, setServerUrl] = useState("");
  const [headers, setHeaders] = useState<{ key: string; value: string }[]>([]);

  const handleAdd = async () => {
    if (!name.trim() || !serverUrl.trim()) return;

    setIsSubmitting(true);

    const headerObj = headers.reduce(
      (acc, { key, value }) => {
        if (key.trim()) acc[key.trim()] = value;
        return acc;
      },
      {} as Record<string, string>
    );

    try {
      await onAdd({
        name: name.trim(),
        transport,
        server_url: serverUrl.trim(),
        headers: headerObj,
        custom: true,
        created_at: new Date().toISOString(),
      });
      setIsModalOpen(false);
      setName("");
      setTransport("streamable-http");
      setServerUrl("");
      setHeaders([]);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <div className="grid gap-2">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wider text-default-400">
            MCPs
          </p>
          <Button
            aria-label="Add MCP"
            isIconOnly
            size="sm"
            variant="ghost"
            onPress={() => setIsModalOpen(true)}
            isDisabled={isBusy}
          >
            <span aria-hidden="true">+</span>
          </Button>
        </div>
        <div className="grid gap-1 rounded-lg border border-default-200/60 px-3 py-2">
          {mcps.length === 0 ? (
            <p className="text-xs text-default-400">No MCPs configured.</p>
          ) : (
            mcps.map((mcp) => (
              <McpCard
                key={mcp.name}
                mcp={mcp}
                isBusy={isBusy}
                onToggle={onToggle}
                onDelete={onDelete}
              />
            ))
          )}
        </div>
      </div>

      <Modal isOpen={isModalOpen} onOpenChange={setIsModalOpen}>
        <Modal.Backdrop variant="blur">
          <Modal.Container size="lg" placement="center">
            <Modal.Dialog>
              <ModalHeader className="items-start justify-between gap-4 border-b border-default-200/60 pb-4">
                <div className="grid gap-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-sm font-semibold text-primary">
                      MCP
                    </div>
                    <div className="grid gap-1">
                      <ModalHeading className="text-base font-semibold">
                        Create Custom MCP
                      </ModalHeading>
                      <p className="text-sm text-default-500">
                        Register a reusable MCP endpoint. It stays disabled for
                        this session until you turn it on.
                      </p>
                    </div>
                  </div>
                </div>
                <ModalCloseTrigger aria-label="Close add MCP modal" />
              </ModalHeader>
              <ModalBody className="grid gap-5 pt-5">
                <div className="grid gap-4 rounded-xl border border-default-200/60 bg-default-50/40 p-4">
                  <div className="grid gap-1">
                    <FieldLabel>Name</FieldLabel>
                    <TextField aria-label="MCP name">
                      <Input
                        aria-label="Name"
                        placeholder="e.g. my-mcp"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                      />
                    </TextField>
                  </div>
                  <div className="grid gap-1">
                    <FieldLabel>Transport</FieldLabel>
                    <Select
                      aria-label="Transport"
                      placeholder="Select transport"
                      value={transport}
                      onChange={(value) => {
                        if (value != null) {
                          setTransport(String(value) as TransportType);
                        }
                      }}
                    >
                      <Select.Trigger aria-label="Transport">
                        <Select.Value />
                        <Select.Indicator />
                      </Select.Trigger>
                      <Select.Popover>
                        <ListBox aria-label="Transport">
                          {SUPPORTED_TRANSPORTS.map((t) => (
                            <ListBoxItem
                              key={t.value}
                              id={t.value}
                              textValue={t.label}
                            >
                              {t.label}
                            </ListBoxItem>
                          ))}
                        </ListBox>
                      </Select.Popover>
                    </Select>
                  </div>
                  <div className="grid gap-1">
                    <FieldLabel>Server URL</FieldLabel>
                    <TextField aria-label="MCP server URL">
                      <Input
                        aria-label="Server URL"
                        placeholder="http://localhost:4000/mcp/"
                        value={serverUrl}
                        onChange={(e) => setServerUrl(e.target.value)}
                      />
                    </TextField>
                  </div>
                </div>
                <div className="grid gap-2 rounded-xl border border-default-200/60 p-4">
                  <div className="grid gap-1">
                    <FieldLabel>Headers</FieldLabel>
                    <p className="text-xs text-default-500">
                      Optional request headers sent with every MCP call.
                    </p>
                  </div>
                  <KeyValuePairEditor pairs={headers} onChange={setHeaders} />
                </div>
              </ModalBody>
              <ModalFooter className="border-t border-default-200/60 pt-4">
                <Button
                  variant="ghost"
                  onPress={() => setIsModalOpen(false)}
                  isDisabled={isSubmitting}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  onPress={handleAdd}
                  isDisabled={isSubmitting || !name.trim() || !serverUrl.trim()}
                >
                  Create MCP
                </Button>
              </ModalFooter>
            </Modal.Dialog>
          </Modal.Container>
        </Modal.Backdrop>
      </Modal>
    </>
  );
}
