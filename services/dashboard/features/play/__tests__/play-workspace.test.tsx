import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import { PlayWorkspace } from "@/features/play/components/play-workspace";
import type {
  ContextMetadata,
  DashboardConfig,
  JobDetail,
  ProviderResponse,
  SessionDetail,
  SessionSummary,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";

const api = vi.hoisted(() => ({
  fetchDashboardConfig: vi.fn(),
  listProviders: vi.fn(),
  listAvailableSkills: vi.fn(),
  listSessions: vi.fn(),
  getSession: vi.fn(),
  listSessionJobs: vi.fn(),
  getJob: vi.fn(),
  getContextMetadata: vi.fn(),
  setModelConfig: vi.fn(),
  createSession: vi.fn(),
  submitPrompt: vi.fn(),
  compactSession: vi.fn(),
  updateSession: vi.fn(),
  addSkill: vi.fn(),
  removeSkill: vi.fn(),
  listSessionMcps: vi.fn(),
  addMcp: vi.fn(),
  removeMcp: vi.fn(),
  terminateSession: vi.fn(),
}));

vi.mock("@/features/play/lib/client-api", () => api);

vi.mock("@heroui/react", () => ({
  Spinner: () => <div>Loading spinner</div>,
}));

vi.mock("@/features/play/components/play-session-list", () => ({
  PlaySessionList: ({ selectedSessionId, sessions, onCreate, onSelect }: { selectedSessionId: string | null; sessions: SessionSummary[]; onCreate: () => void; onSelect: (id: string | null) => void }) => (
    <div>
      <button type="button" onClick={onCreate}>Create session</button>
      <div data-testid="selected-session-id">{selectedSessionId ?? "none"}</div>
      {sessions.map((session) => (
        <button key={session.id} type="button" onClick={() => onSelect(session.id)}>
          {session.name}
        </button>
      ))}
    </div>
  ),
}));

vi.mock("@/features/play/components/play-transcript", () => ({
  PlayTranscript: ({ jobs, statusText, errorText, streamState, selectedSession, onOpenSettings, settingsOpen }: { jobs: JobDetail[]; statusText: string; errorText: string | null; streamState: string; selectedSession: SessionDetail | null; onOpenSettings: () => void; settingsOpen: boolean }) => (
    <div>
      <div data-testid="status-text">{statusText}</div>
      <div data-testid="error-text">{errorText ?? ""}</div>
      <div data-testid="stream-state">{streamState}</div>
      <div data-testid="selected-session-name">{selectedSession?.name ?? "none"}</div>
      <div data-testid="job-count">{jobs.length}</div>
      <button type="button" onClick={onOpenSettings}>{settingsOpen ? "close settings" : "open settings"}</button>
    </div>
  ),
}));

vi.mock("@/features/play/components/play-prompt-box", () => ({
  PlayPromptBox: ({ prompt, selectedSession, onPromptChange, onSubmit, onCompact }: { prompt: string; selectedSession: SessionDetail | null; onPromptChange: (value: string) => void; onSubmit: () => void; onCompact: () => void }) => (
    <div>
      <div data-testid="prompt-session">{selectedSession?.id ?? "none"}</div>
      <input aria-label="Prompt input" value={prompt} onChange={(event) => onPromptChange(event.target.value)} />
      <button type="button" onClick={onSubmit}>Submit prompt</button>
      <button type="button" onClick={onCompact}>Compact context</button>
    </div>
  ),
}));

vi.mock("@/features/play/components/play-config-panel", () => ({
  PlayConfigPanel: ({ draft, modelOptions, providers, skills, isOpen, onDraftChange, onSave, onTerminate, onClose }: { draft: { providerId: string; modelName: string; name: string }; modelOptions: string[]; providers: ProviderResponse[]; skills: SkillDefinitionResponse[]; isOpen: boolean; onDraftChange: (draft: { providerId: string; modelName: string; name: string; reasoning: { enabled: boolean; effort: "low" | "medium" | "high"; maxTokens: string }; gatewayOptionsText: string; providerOptionsText: string; selectedSkills: string[]; enableDefaultGameServiceMcp: boolean; customMcpsText: string }) => void; onSave: () => void; onTerminate: () => void; onClose: () => void }) => (
    <div>
      <div data-testid="config-open">{String(isOpen)}</div>
      <div data-testid="draft-provider">{draft.providerId}</div>
      <div data-testid="draft-model">{draft.modelName}</div>
      <div data-testid="provider-count">{providers.length}</div>
      <div data-testid="skill-count">{skills.length}</div>
      <div data-testid="model-options">{modelOptions.join(",")}</div>
      <button
        type="button"
        onClick={() => onDraftChange({ ...draft, providerId: "anthropic", modelName: "claude-3-5-haiku" })}
      >
        Change provider
      </button>
      <button type="button" onClick={onSave}>Save configuration</button>
      <button type="button" onClick={onTerminate}>Terminate session</button>
      <button type="button" onClick={onClose}>Close panel</button>
    </div>
  ),
}));

const baseConfig: DashboardConfig = {
  appName: "Dashboard",
  defaultProviderId: "openai",
  defaultModelName: "gpt-4o-mini",
  defaultGameServiceMcpEnabled: true,
  defaultGameServiceMcpName: "game-service",
  defaultGameServiceMcpTransport: "streamable-http",
  defaultGameServiceMcpUrl: "http://game-service/mcp",
  defaultSkills: ["skill-a"],
  defaultCustomMcps: [],
};

const providers: ProviderResponse[] = [
  { provider_id: "openai", model_prefix: "openai", models: ["gpt-4o-mini", "gpt-4o-mini"], available: true, error: null },
  { provider_id: "anthropic", model_prefix: "anthropic", models: ["claude-3-5-haiku"], available: true, error: null },
  { provider_id: "openai", model_prefix: "openai", models: ["gpt-4o-mini"], available: true, error: null },
];

const skills: SkillDefinitionResponse[] = [
  { name: "skill-a", path: "/skills/a", content_markdown: "a" },
  { name: "skill-b", path: "/skills/b", content_markdown: "b" },
];

const sessionSummary: SessionSummary = {
  id: "session-1",
  name: "Existing session",
  status: "active",
  metadata: {},
  created_at: "2026-05-11T00:00:00Z",
  updated_at: "2026-05-11T00:00:00Z",
  terminated_at: null,
  model_config: null,
  skills: [],
  mcps: [],
  recent_job: null,
};

const sessionDetail: SessionDetail = {
  ...sessionSummary,
  model_config: {
    provider_id: "openai",
    model_name: "gpt-4o-mini",
    gateway_options: {},
    provider_options: {},
    updated_at: "2026-05-11T00:00:00Z",
  },
  recent_jobs: [],
};

const job: JobDetail = {
  id: "job-1",
  prompt_run_id: "prompt-run-1",
  status: "completed",
  attempts: 1,
  max_attempts: 1,
  error_code: null,
  error_message: null,
  result_text: null,
  cancellation_requested_at: null,
  created_at: "2026-05-11T00:00:00Z",
  started_at: "2026-05-11T00:00:01Z",
  completed_at: "2026-05-11T00:00:02Z",
  latest_event_id: "event-1",
  latest_event_type: "completion",
  prompt_run: {
    id: "prompt-run-1",
    prompt: "Hi",
    status: "completed",
    metadata: {},
    created_at: "2026-05-11T00:00:00Z",
    updated_at: "2026-05-11T00:00:02Z",
  },
  outputs: [],
  events: [],
  available_tools: [],
};

const contextMetadata: ContextMetadata = {
  tokens_used: 10,
  context_window_size: 100,
  usage_ratio: 0.1,
  compaction_count: 0,
  last_compacted_at: null,
  multi_turn_memory: true,
};

function createStorageMock() {
  const store = new Map<string, string>();
  return {
    getItem: vi.fn((key: string) => store.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store.set(key, value);
    }),
    removeItem: vi.fn((key: string) => {
      store.delete(key);
    }),
    clear: vi.fn(() => {
      store.clear();
    }),
  };
}

class MockEventSource {
  static instances: MockEventSource[] = [];
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public readonly url: string) {
    MockEventSource.instances.push(this);
  }

  addEventListener() {}

  close() {}
}

function installMatchMedia(matches = false) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches,
      media: "(max-width: 767px)",
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe("PlayWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installMatchMedia(false);
    MockEventSource.instances = [];

    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: createStorageMock(),
    });
    Object.defineProperty(globalThis, "EventSource", {
      configurable: true,
      value: MockEventSource,
    });

    api.fetchDashboardConfig.mockResolvedValue(baseConfig);
    api.listProviders.mockResolvedValue(providers);
    api.listAvailableSkills.mockResolvedValue(skills);
    api.listSessions.mockResolvedValue([sessionSummary]);
    api.getSession.mockResolvedValue(sessionDetail);
    api.listSessionJobs.mockResolvedValue({ jobs: [{ ...job, events: undefined, prompt_run: undefined, outputs: undefined, available_tools: undefined }], page: { total: 1, limit: 50, offset: 0 } });
    api.getJob.mockResolvedValue(job);
    api.getContextMetadata.mockResolvedValue(contextMetadata);
    api.setModelConfig.mockResolvedValue({ model_config: {} });
    api.createSession.mockResolvedValue({ ...sessionDetail, id: "session-2", name: "Created" });
    api.submitPrompt.mockResolvedValue({ ...job, events: undefined, prompt_run: undefined, outputs: undefined, available_tools: undefined });
    api.compactSession.mockResolvedValue(contextMetadata);
    api.updateSession.mockResolvedValue(sessionDetail);
    api.addSkill.mockResolvedValue({});
    api.removeSkill.mockResolvedValue(undefined);
    api.listSessionMcps.mockResolvedValue([]);
    api.addMcp.mockResolvedValue({});
    api.removeMcp.mockResolvedValue(undefined);
    api.terminateSession.mockResolvedValue({ ...sessionDetail, status: "terminated" });
  });

  it("loads config, restores saved session, and avoids syncing unchanged model config", async () => {
    globalThis.localStorage.setItem("play:selectedSessionId", "session-1");

    render(<PlayWorkspace />);

    await waitFor(() => expect(screen.getByTestId("selected-session-id")).toHaveTextContent("session-1"));
    await waitFor(() => expect(screen.getByTestId("selected-session-name")).toHaveTextContent("Existing session"));
    expect(screen.getByTestId("job-count")).toHaveTextContent("1");
    expect(screen.getByTestId("provider-count")).toHaveTextContent("2");
    expect(screen.getByTestId("model-options")).toHaveTextContent("gpt-4o-mini");
    expect(api.setModelConfig).not.toHaveBeenCalled();
  });

  it("switches to mobile defaults on first render", async () => {
    installMatchMedia(true);

    render(<PlayWorkspace />);

    await waitFor(() => expect(screen.getByTestId("config-open")).toHaveTextContent("false"));
  });

  it("syncs model config when the draft provider changes", async () => {
    render(<PlayWorkspace />);

    await waitFor(() => expect(screen.getByTestId("draft-provider")).toHaveTextContent("openai"));
    fireEvent.click(screen.getByRole("button", { name: /change provider/i }));

    await waitFor(() => {
      expect(api.setModelConfig).toHaveBeenCalledWith("session-1", expect.objectContaining({
        provider_id: "anthropic",
        model_name: "claude-3-5-haiku",
      }));
    });
  });

  it("creates a session, selects it, and persists the selection", async () => {
    api.listSessions
      .mockResolvedValueOnce([sessionSummary])
      .mockResolvedValueOnce([{ ...sessionSummary, id: "session-2", name: "Created" }]);

    render(<PlayWorkspace />);

    await waitFor(() => expect(screen.getByTestId("selected-session-id")).toHaveTextContent("session-1"));
    fireEvent.click(screen.getByRole("button", { name: /create session/i }));

    await waitFor(() => expect(api.createSession).toHaveBeenCalled());
    await waitFor(() => expect(globalThis.localStorage.getItem("play:selectedSessionId")).toBe("session-2"));
  });

  it("submits a prompt and refreshes the job list", async () => {
    api.submitPrompt.mockResolvedValueOnce({
      id: "job-2",
      prompt_run_id: "prompt-run-2",
      status: "queued",
      attempts: 1,
      max_attempts: 1,
      error_code: null,
      error_message: null,
      result_text: null,
      cancellation_requested_at: null,
      created_at: "2026-05-11T00:00:03Z",
      started_at: null,
      completed_at: null,
      latest_event_id: null,
      latest_event_type: null,
    });
    api.getJob.mockResolvedValueOnce(job).mockResolvedValueOnce({ ...job, id: "job-2", status: "queued" });

    render(<PlayWorkspace />);

    await waitFor(() => expect(screen.getByTestId("prompt-session")).toHaveTextContent("session-1"));
    fireEvent.change(screen.getByLabelText("Prompt input"), { target: { value: "Hello world" } });
    fireEvent.click(screen.getByRole("button", { name: /submit prompt/i }));

    await waitFor(() => expect(api.submitPrompt).toHaveBeenCalledWith("session-1", "Hello world"));
  });

  it("compacts context and reloads jobs", async () => {
    render(<PlayWorkspace />);

    await waitFor(() => expect(screen.getByTestId("prompt-session")).toHaveTextContent("session-1"));
    fireEvent.click(screen.getByRole("button", { name: /compact context/i }));

    await waitFor(() => expect(api.compactSession).toHaveBeenCalledWith("session-1"));
    expect(api.listSessionJobs).toHaveBeenCalledWith("session-1");
  });
});
