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
  cancelJob: vi.fn(),
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
vi.mock("@heroui/react", () => ({ Spinner: () => <div>Loading spinner</div> }));
vi.mock("@/features/play/components/subagent-list", () => ({
  SubagentList: () => null,
}));
vi.mock("@/features/play/components/subagent-output-modal", () => ({
  SubagentOutputModal: () => null,
}));
vi.mock("@/features/play/components/play-session-list", () => ({
  PlaySessionList: ({ selectedSessionId }: { selectedSessionId: string | null }) => (
    <div data-testid="selected-session-id">{selectedSessionId ?? "none"}</div>
  ),
}));
vi.mock("@/features/play/components/play-transcript", () => ({
  PlayTranscript: ({ streamState }: { streamState: string }) => (
    <div data-testid="stream-state">{streamState}</div>
  ),
}));
vi.mock("@/features/play/components/play-prompt-box", () => ({
  PlayPromptBox: ({
    prompt,
    activeJobId,
    cancelPending,
    onPromptChange,
    onSubmit,
    onCancelExecution,
    onCompact,
  }: {
    prompt: string;
    activeJobId: string | null;
    cancelPending: boolean;
    onPromptChange: (value: string) => void;
    onSubmit: () => void;
    onCancelExecution: () => void;
    onCompact: () => void;
  }) => (
    <div>
      <div data-testid="active-job-id">{activeJobId ?? "none"}</div>
      <div data-testid="cancel-pending">{String(cancelPending)}</div>
      <input
        aria-label="Prompt input"
        value={prompt}
        onChange={(event) => onPromptChange(event.target.value)}
      />
      <button type="button" onClick={onSubmit}>
        Submit prompt
      </button>
      <button type="button" onClick={onCancelExecution}>
        Cancel execution
      </button>
      <button type="button" onClick={onCompact}>
        Compact context
      </button>
    </div>
  ),
}));
vi.mock("@/features/play/components/play-config-panel", () => ({
  PlayConfigPanel: ({ onSave }: { onSave: () => void }) => (
    <button type="button" onClick={onSave}>
      Save configuration
    </button>
  ),
}));

const baseConfig: DashboardConfig = {
  appName: "Dashboard",
  defaultProviderId: "openai",
  defaultModelName: "gpt-4o-mini",
  defaultGameServiceMcpEnabled: true,
  defaultGameServiceMcpName: "game-service",
  defaultGameServiceMcpTransport: "streamable-http",
  defaultGameServiceMcpUrl: "http://game-service:8000/mcp/",
  defaultSkills: ["skill-a"],
  defaultCustomMcps: [],
};

const providers: ProviderResponse[] = [
  {
    provider_id: "openai",
    model_prefix: "openai",
    models: ["gpt-4o-mini"],
    available: true,
    error: null,
  },
];

const skills: SkillDefinitionResponse[] = [
  { name: "skill-a", path: "/skills/a", description: "Skill A", metadata: {} },
];

const sessionSummary: SessionSummary = {
  id: "session-1",
  name: "Existing session",
  status: "active",
  context_recent_message_limit: null,
  context_recent_tool_exchange_limit: null,
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
  prompt: "Hi",
  metadata: {},
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
  token_breakdown: { system_prompt: 2, replay: 5, tools: 3 },
};

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation(() => ({
      matches: false,
      media: "(max-width: 767px)",
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  Object.defineProperty(globalThis, "EventSource", {
    configurable: true,
    value: class {
      onmessage = null;
      onerror = null;
      addEventListener() {}
      close() {}
    },
  });

  api.fetchDashboardConfig.mockResolvedValue(baseConfig);
  api.listProviders.mockResolvedValue(providers);
  api.listAvailableSkills.mockResolvedValue(skills);
  api.listSessions.mockResolvedValue([sessionSummary]);
  api.getSession.mockResolvedValue(sessionDetail);
  api.listSessionJobs.mockResolvedValue({
    jobs: [
      {
        ...job,
        events: undefined,
        outputs: undefined,
        available_tools: undefined,
      },
    ],
    page: { total: 1, limit: 50, offset: 0 },
  });
  api.getJob.mockResolvedValue(job);
  api.getContextMetadata.mockResolvedValue(contextMetadata);
  api.setModelConfig.mockResolvedValue({ model_config: {} });
  api.createSession.mockResolvedValue(sessionDetail);
  api.submitPrompt.mockResolvedValue({ ...job, id: "job-2", status: "queued" });
  api.cancelJob.mockResolvedValue({
    ...job,
    id: "job-2",
    status: "running",
    cancellation_requested_at: "2026-05-11T00:00:04Z",
    latest_event_type: "progress",
  });
  api.compactSession.mockResolvedValue(contextMetadata);
  api.updateSession.mockResolvedValue(sessionDetail);
  api.addSkill.mockResolvedValue({});
  api.removeSkill.mockResolvedValue(undefined);
  api.listSessionMcps.mockResolvedValue([]);
  api.addMcp.mockResolvedValue({});
  api.removeMcp.mockResolvedValue(undefined);
  api.terminateSession.mockResolvedValue({ ...sessionDetail, status: "terminated" });
});

describe("PlayWorkspace execution paths", () => {
  it("shows loading spinner while dashboard config is pending", () => {
    api.fetchDashboardConfig.mockReturnValue(new Promise(() => undefined));

    render(<PlayWorkspace />);

    expect(screen.getByText("Loading spinner")).toBeInTheDocument();
  });

  it("submits a prompt and shows streaming state", async () => {
    api.getJob
      .mockResolvedValueOnce(job)
      .mockResolvedValueOnce({ ...job, id: "job-2", status: "queued" });

    render(<PlayWorkspace />);

    await waitFor(() =>
      expect(screen.getByTestId("selected-session-id")).toHaveTextContent("session-1")
    );
    fireEvent.change(screen.getByLabelText("Prompt input"), {
      target: { value: "Hello world" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit prompt/i }));

    await waitFor(() =>
      expect(api.submitPrompt).toHaveBeenCalledWith("session-1", "Hello world")
    );
    expect(screen.getByRole("status", { name: /streaming response/i })).toBeInTheDocument();
    expect(screen.getByTestId("active-job-id")).toHaveTextContent("job-2");
  });

  it("requests cancellation for active execution", async () => {
    api.getJob
      .mockResolvedValueOnce(job)
      .mockResolvedValueOnce({ ...job, id: "job-2", status: "queued" });

    render(<PlayWorkspace />);

    await waitFor(() =>
      expect(screen.getByTestId("selected-session-id")).toHaveTextContent("session-1")
    );
    fireEvent.change(screen.getByLabelText("Prompt input"), {
      target: { value: "Hello world" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit prompt/i }));

    await waitFor(() =>
      expect(screen.getByTestId("active-job-id")).toHaveTextContent("job-2")
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel execution/i }));

    await waitFor(() => expect(api.cancelJob).toHaveBeenCalledWith("job-2"));
    await waitFor(() =>
      expect(screen.getByTestId("cancel-pending")).toHaveTextContent("true")
    );
  });

  it("compacts context and reloads jobs", async () => {
    render(<PlayWorkspace />);

    await waitFor(() =>
      expect(screen.getByTestId("selected-session-id")).toHaveTextContent("session-1")
    );
    fireEvent.click(screen.getByRole("button", { name: /compact context/i }));

    await waitFor(() => expect(api.compactSession).toHaveBeenCalledWith("session-1"));
    expect(api.listSessionJobs).toHaveBeenCalledWith("session-1");
  });

  it("saves replay window settings with session update", async () => {
    api.getSession.mockResolvedValueOnce({
      ...sessionDetail,
      context_recent_message_limit: 5,
      context_recent_tool_exchange_limit: 2,
    });

    render(<PlayWorkspace />);

    await waitFor(() =>
      expect(screen.getByTestId("selected-session-id")).toHaveTextContent("session-1")
    );
    fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));

    await waitFor(() =>
      expect(api.updateSession).toHaveBeenCalledWith(
        "session-1",
        expect.objectContaining({
          context_recent_message_limit: 5,
          context_recent_tool_exchange_limit: 2,
        })
      )
    );
  });
});
