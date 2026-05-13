export type SessionDetailResponse = {
  session: {
    id: string;
    model_config: { provider_id: string; model_name: string } | null;
    mcps: Array<{ name: string }>;
  };
};

export type SessionListResponse = {
  sessions: Array<{
    id: string;
    created_at: string;
  }>;
};

export type SessionJobsResponse = {
  jobs: Array<{
    id: string;
    status: string;
    error_message: string | null;
    created_at: string;
  }>;
};

export type JobEventsResponse = {
  events: Array<{
    event_type: string;
    payload: Record<string, unknown>;
  }>;
};

export type SessionToolsResponse = {
  tools: Array<{ name: string }>;
};
