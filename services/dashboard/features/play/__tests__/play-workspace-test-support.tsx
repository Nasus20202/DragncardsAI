import { render } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";

import { PlayWorkspace } from "@/features/play/components/play-workspace";
import type {
  ContextMetadata,
  DashboardConfig,
  JobDetail,
  ProviderResponse,
  SessionDetail,
  SessionDraft,
  SessionSummary,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";

const apiMocks = vi.hoisted(() => ({
  fetchDashboardConfig: vi.fn(),
  listProviders: vi.fn(),
  listAvailableSkills: vi.fn(),
  listSessions: vi.fn(),
  getSession: vi.fn(),
  listSessionJobs: vi.fn(),
  getJob: vi.fn(),
  answerUserQuestion: vi.fn(),
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
  removeMcpRegistry: vi.fn(),
  terminateSession: vi.fn(),
  deleteSession: vi.fn(),
}));

vi.mock("@/features/play/lib/client-api", () => apiMocks);

export function getApi() {
  return apiMocks;
}

type MockChildrenProps = {
  children?: React.ReactNode;
  className?: string;
};

// PlayWorkspace renders the (unmocked) RemoveSessionModal, so the Hero UI mock
// has to cover the Modal compound parts and Button it uses.
vi.mock("@heroui/react", () => ({
  Spinner: () => <div>Loading spinner</div>,
  Button: ({
    children,
    onPress,
    isDisabled,
    "data-testid": dataTestId,
  }: MockChildrenProps & {
    onPress?: () => void;
    isDisabled?: boolean;
    "data-testid"?: string;
  }) => (
    <button
      data-testid={dataTestId}
      disabled={isDisabled}
      type="button"
      onClick={onPress}
    >
      {children}
    </button>
  ),
  Modal: Object.assign(
    ({ children, isOpen }: MockChildrenProps & { isOpen?: boolean }) =>
      isOpen === false ? null : <div>{children}</div>,
    {
      Backdrop: ({ children }: MockChildrenProps) => <div>{children}</div>,
      Container: ({ children }: MockChildrenProps) => <div>{children}</div>,
      Dialog: ({
        children,
        "aria-label": ariaLabel,
      }: MockChildrenProps & { "aria-label"?: string }) => (
        <div aria-label={ariaLabel} aria-modal="true" role="dialog">
          {children}
        </div>
      ),
    }
  ),
  ModalHeader: ({ children }: MockChildrenProps) => <div>{children}</div>,
  ModalHeading: ({ children }: MockChildrenProps) => <h2>{children}</h2>,
  ModalBody: ({ children }: MockChildrenProps) => <div>{children}</div>,
  ModalFooter: ({ children }: MockChildrenProps) => <div>{children}</div>,
}));

vi.mock("@/features/play/components/play-session-list", () => ({
  PlaySessionList: ({
    selectedSessionId,
    sessions,
    onCreate,
    onSelect,
    onRemove,
  }: {
    selectedSessionId: string | null;
    sessions: SessionSummary[];
    onCreate: () => void;
    onSelect: (id: string | null) => void;
    onRemove?: (id: string) => void;
  }) => (
    <div>
      <button type="button" onClick={onCreate}>
        Create session
      </button>
      <div data-testid="selected-session-id">{selectedSessionId ?? "none"}</div>
      <div data-testid="visible-session-ids">
        {sessions.map((session) => session.id).join(",")}
      </div>
      {sessions.map((session) => (
        <div key={session.id}>
          <button type="button" onClick={() => onSelect(session.id)}>
            {session.name}
          </button>
          <button
            type="button"
            data-testid={`remove-${session.id}`}
            aria-label={`remove-${session.id}`}
            onClick={() => onRemove?.(session.id)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  ),
}));

vi.mock("@/features/play/components/play-transcript", () => ({
  PlayTranscript: ({
    jobs,
    statusText,
    errorText,
    streamState,
    selectedSession,
    onOpenSettings,
    settingsOpen,
  }: {
    jobs: JobDetail[];
    statusText: string;
    errorText: string | null;
    streamState: string;
    selectedSession: SessionDetail | null;
    onOpenSettings: () => void;
    settingsOpen: boolean;
  }) => (
    <div>
      <div data-testid="status-text">{statusText}</div>
      <div data-testid="error-text">{errorText ?? ""}</div>
      <div data-testid="stream-state">{streamState}</div>
      <div data-testid="selected-session-name">
        {selectedSession?.name ?? "none"}
      </div>
      <div data-testid="selected-session-mcp-count">
        {selectedSession?.mcps.length ?? 0}
      </div>
      <div data-testid="job-count">{jobs.length}</div>
      <button type="button" onClick={onOpenSettings}>
        {settingsOpen ? "close settings" : "open settings"}
      </button>
    </div>
  ),
}));

vi.mock("@/features/play/components/play-prompt-box", () => ({
  PlayPromptBox: ({
    prompt,
    selectedSession,
    activeJobId,
    cancelPending,
    attachedSkills,
    onPromptChange,
    onSubmit,
    onCancelExecution,
    onCompact,
    onAttachSkill,
    onDetachSkill,
  }: {
    prompt: string;
    selectedSession: SessionDetail | null;
    activeJobId: string | null;
    cancelPending: boolean;
    attachedSkills: string[];
    onPromptChange: (value: string) => void;
    onSubmit: () => void;
    onCancelExecution: () => void;
    onCompact: () => void;
    onAttachSkill: (skillName: string) => void;
    onDetachSkill: (skillName: string) => void;
  }) => (
    <div>
      <div data-testid="prompt-session">{selectedSession?.id ?? "none"}</div>
      <div data-testid="active-job-id">{activeJobId ?? "none"}</div>
      <div data-testid="cancel-pending">{String(cancelPending)}</div>
      <div data-testid="prompt-attached-skills">{attachedSkills.join(",")}</div>
      {["skill-a", "skill-b"].map((skillName) => (
        <div key={skillName}>
          <button type="button" onClick={() => onAttachSkill(skillName)}>
            {`Attach ${skillName}`}
          </button>
          <button type="button" onClick={() => onDetachSkill(skillName)}>
            {`Detach ${skillName}`}
          </button>
        </div>
      ))}
      <input
        aria-label="Prompt input"
        value={prompt}
        onChange={(event) => onPromptChange(event.target.value)}
      />
      <button type="button" onClick={onSubmit}>
        Submit prompt
      </button>
      <button
        type="button"
        disabled={!activeJobId || cancelPending}
        onClick={onCancelExecution}
      >
        Cancel execution
      </button>
      <button type="button" onClick={onCompact}>
        Compact context
      </button>
    </div>
  ),
}));

vi.mock("@/features/play/components/play-config-panel", () => ({
  PlayConfigPanel: ({
    draft,
    modelOptions,
    providers,
    skills,
    isOpen,
    onDraftChange,
    onSave,
    onTerminate,
    onClose,
  }: {
    draft: SessionDraft;
    modelOptions: string[];
    providers: ProviderResponse[];
    skills: SkillDefinitionResponse[];
    isOpen: boolean;
    onDraftChange: (draft: SessionDraft) => void;
    onSave: () => void;
    onTerminate: () => void;
    onClose: () => void;
  }) => (
    <div>
      <div data-testid="config-open">{String(isOpen)}</div>
      <div data-testid="draft-provider">{draft.providerId}</div>
      <div data-testid="draft-model">{draft.modelName}</div>
      <div data-testid="draft-skills">{draft.selectedSkills.join(",")}</div>
      <div data-testid="draft-reasoning">
        {`${draft.reasoning.enabled}:${draft.reasoning.effort}`}
      </div>
      <div data-testid="draft-gateway-options">{draft.gatewayOptionsText}</div>
      <div data-testid="draft-message-limit">{draft.recentMessageLimit}</div>
      <div data-testid="provider-count">{providers.length}</div>
      <div data-testid="skill-count">{skills.length}</div>
      <div data-testid="model-options">{modelOptions.join(",")}</div>
      <button
        type="button"
        onClick={() =>
          onDraftChange({
            ...draft,
            providerId: "anthropic",
            modelName: "claude-3-5-haiku",
          })
        }
      >
        Change provider
      </button>
      <button
        type="button"
        onClick={() =>
          onDraftChange({
            ...draft,
            selectedSkills: [...draft.selectedSkills, "skill-b"],
          })
        }
      >
        Enable skill-b in settings
      </button>
      <button type="button" onClick={onSave}>
        Save configuration
      </button>
      <button type="button" onClick={onTerminate}>
        Terminate session
      </button>
      <button type="button" onClick={onClose}>
        Close panel
      </button>
    </div>
  ),
}));

export const baseConfig: DashboardConfig = {
  appName: "Dashboard",
  defaultProviderId: "openai",
  defaultModelName: "gpt-4o-mini",
  defaultGameServiceMcpEnabled: true,
  defaultGameServiceMcpName: "game-service",
  defaultGameServiceMcpTransport: "streamable-http",
  defaultGameServiceMcpUrl: "http://game-service:8000/mcp/",
  defaultSkills: ["skill-a"],
  defaultCustomMcps: [],
  dragncardsFrontendUrl: "http://localhost:4000",
  bifrostUiUrl: "http://localhost:4003",
  defaultReasoningEnabled: false,
  defaultReasoningEffort: "medium",
};

export const providers: ProviderResponse[] = [
  {
    provider_id: "openai",
    model_prefix: "openai",
    models: ["gpt-4o-mini", "gpt-4o-mini"],
    available: true,
    error: null,
  },
  {
    provider_id: "anthropic",
    model_prefix: "anthropic",
    models: ["claude-3-5-haiku"],
    available: true,
    error: null,
  },
  {
    provider_id: "openai",
    model_prefix: "openai",
    models: ["gpt-4o-mini"],
    available: true,
    error: null,
  },
];

export const skills: SkillDefinitionResponse[] = [
  { name: "skill-a", path: "/skills/a", description: "Skill A", metadata: {} },
  { name: "skill-b", path: "/skills/b", description: "Skill B", metadata: {} },
];

export const sessionSummary: SessionSummary = {
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

export const sessionDetail: SessionDetail = {
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

export const job: JobDetail = {
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

export const contextMetadata: ContextMetadata = {
  tokens_used: 10,
  context_window_size: 100,
  usage_ratio: 0.1,
  compaction_count: 0,
  last_compacted_at: null,
  multi_turn_memory: true,
  token_breakdown: {
    system_prompt: 2,
    replay: 5,
    tools: 3,
  },
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

export function installMatchMedia(matches = false) {
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

export function resetPlayWorkspaceEnvironment() {
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

  apiMocks.fetchDashboardConfig.mockResolvedValue(baseConfig);
  apiMocks.listProviders.mockResolvedValue(providers);
  apiMocks.listAvailableSkills.mockResolvedValue(skills);
  apiMocks.listSessions.mockResolvedValue([sessionSummary]);
  apiMocks.getSession.mockResolvedValue(sessionDetail);
  apiMocks.listSessionJobs.mockResolvedValue({
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
  apiMocks.getJob.mockResolvedValue(job);
  apiMocks.getContextMetadata.mockResolvedValue(contextMetadata);
  apiMocks.setModelConfig.mockResolvedValue({ model_config: {} });
  apiMocks.createSession.mockResolvedValue({
    ...sessionDetail,
    id: "session-2",
    name: "Created",
  });
  apiMocks.submitPrompt.mockResolvedValue({
    ...job,
    events: undefined,
    outputs: undefined,
    available_tools: undefined,
  });
  apiMocks.cancelJob.mockResolvedValue({
    ...job,
    id: "job-2",
    status: "running",
    cancellation_requested_at: "2026-05-11T00:00:04Z",
    latest_event_type: "progress",
  });
  apiMocks.compactSession.mockResolvedValue(contextMetadata);
  apiMocks.updateSession.mockResolvedValue(sessionDetail);
  apiMocks.addSkill.mockResolvedValue({});
  apiMocks.removeSkill.mockResolvedValue(undefined);
  apiMocks.listSessionMcps.mockResolvedValue([]);
  apiMocks.addMcp.mockResolvedValue({});
  apiMocks.removeMcp.mockResolvedValue(undefined);
  apiMocks.removeMcpRegistry.mockResolvedValue(undefined);
  apiMocks.terminateSession.mockResolvedValue({
    ...sessionDetail,
    status: "terminated",
  });
  apiMocks.deleteSession.mockResolvedValue(undefined);
  window.history.replaceState({}, "", "/play");
}

export function createQueuedJob(overrides: Partial<JobDetail> = {}): JobDetail {
  return {
    ...job,
    id: "job-2",
    prompt: "Hello",
    status: "queued",
    cancellation_requested_at: null,
    created_at: "2026-05-11T00:00:03Z",
    started_at: null,
    completed_at: null,
    latest_event_id: null,
    latest_event_type: null,
    ...overrides,
  };
}

export function renderPlayWorkspace() {
  return render(<PlayWorkspace />);
}
