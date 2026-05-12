import { SessionSummary } from "@/features/shared/lib/types";

function dotColor(status: string | null | undefined) {
  switch (status) {
    case "completed":
      return "bg-success";
    case "running":
      return "bg-warning animate-pulse";
    case "failed":
      return "bg-danger";
    default:
      return "bg-default-300";
  }
}

function shortModel(model: string | null | undefined) {
  if (!model) return "No model";
  // "openrouter/openrouter/free" → "free"
  const parts = model.split("/");
  return parts[parts.length - 1];
}

function shortName(name: string | null | undefined) {
  if (!name) return "Untitled";
  // strip the "session-<uuid>" prefix if that's all it is
  if (name.startsWith("session-")) return name.slice(0, 22) + "…";
  return name;
}

export function PlaySessionList({
  sessions,
  selectedSessionId,
  streamingSessionId,
  isBusy,
  canCreate,
  isCollapsed,
  onCreate,
  onToggleCollapsed,
  onSelect,
}: {
  sessions: SessionSummary[];
  selectedSessionId: string | null;
  streamingSessionId: string | null;
  isBusy: boolean;
  canCreate: boolean;
  isCollapsed: boolean;
  onCreate: () => void;
  onToggleCollapsed: () => void;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="flex h-full flex-col">
      {/* ── Toolbar ───────────────────────────────────────────── */}
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-default-200/60 px-2">
        {!isCollapsed && (
          <span className="truncate px-1 text-xs font-semibold uppercase tracking-widest text-default-400">
            Sessions
          </span>
        )}
        <div
          className={`flex items-center gap-1 ${isCollapsed ? "w-full justify-center" : ""}`}
        >
          <button
            aria-label="New session"
            disabled={isBusy || !canCreate}
            type="button"
            className="flex h-7 items-center gap-1 rounded px-2 text-xs font-medium text-default-500 transition-colors hover:bg-default-100 hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
            onClick={onCreate}
          >
            {isCollapsed ? "+" : "+ New"}
          </button>
          <button
            aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            type="button"
            className="flex h-7 w-7 items-center justify-center rounded text-default-400 transition-colors hover:bg-default-100 hover:text-foreground"
            onClick={onToggleCollapsed}
          >
            <span aria-hidden="true">{isCollapsed ? "›" : "‹"}</span>
          </button>
        </div>
      </div>

      {/* ── Session list ──────────────────────────────────────── */}
      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {sessions.length === 0 && !isCollapsed && (
          <p className="px-3 py-3 text-xs text-default-400">No sessions yet.</p>
        )}

        {sessions.map((s) => {
          const active = s.id === selectedSessionId;
          const isStreaming = s.id === streamingSessionId;
          const jobStatus = s.recent_job?.status ?? null;

          return (
            <button
              key={s.id}
              aria-label={s.name ?? "Untitled session"}
              aria-current={active ? "true" : undefined}
              type="button"
              className={[
                "w-full text-left transition-colors",
                isCollapsed
                  ? "flex justify-center px-2 py-3"
                  : "flex items-center gap-2.5 px-3 py-2.5",
                active
                  ? "bg-default-100 text-foreground"
                  : "text-default-600 hover:bg-default-100/60 hover:text-foreground",
              ].join(" ")}
              onClick={() => onSelect(s.id)}
            >
              {/* Status dot — streaming overrides job status */}
              {isStreaming ? (
                <span
                  aria-hidden="true"
                  className="mt-0.5 h-2 w-2 shrink-0 animate-ping rounded-full bg-success"
                />
              ) : (
                <span
                  aria-hidden="true"
                  className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${dotColor(jobStatus)}`}
                />
              )}

              {!isCollapsed && (
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium leading-tight">
                    {shortName(s.name)}
                  </div>
                  <div className="mt-0.5 truncate text-xs text-default-400">
                    {shortModel(s.model_config?.model_name)} ·{" "}
                    {isStreaming ? "streaming…" : s.status}
                  </div>
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
