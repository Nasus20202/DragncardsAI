import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { GamesWorkspace } from "@/features/games/components/games-workspace";
import * as clientApi from "@/features/play/lib/client-api";
import { DashboardConfig, GameSession } from "@/features/shared/lib/types";

vi.mock("@/features/play/lib/client-api");
vi.mock("@/features/shared/lib/types", async () => {
  const actual = await vi.importActual("@/features/shared/lib/types");
  return actual;
});

const mockConfig: DashboardConfig = {
  appName: "Test Dashboard",
  defaultProviderId: "openai",
  defaultModelName: "gpt-4o-mini",
  defaultGameServiceMcpEnabled: true,
  defaultGameServiceMcpName: "game-service",
  defaultGameServiceMcpTransport: "streamable-http",
  defaultGameServiceMcpUrl: "http://localhost:4001/mcp/",
  defaultSkills: [],
  defaultCustomMcps: [],
  dragncardsFrontendUrl: "http://localhost:4000",
};

const mockGames: GameSession[] = [
  {
    id: "game-123",
    plugin: "marvel-champions",
    plugin_id: 1,
    created_at: "2026-05-18T00:00:00Z",
    room_slug: "lively-fog-1234",
  },
];

describe("GamesWorkspace", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("renders game list and iframe", async () => {
    vi.mocked(clientApi.fetchDashboardConfig).mockResolvedValue(mockConfig);
    vi.mocked(clientApi.listGames).mockResolvedValue(mockGames);

    render(<GamesWorkspace />);

    expect(await screen.findByText("lively-fog-1234")).toBeInTheDocument();
  });

  it("shows loading state initially", () => {
    vi.mocked(clientApi.fetchDashboardConfig).mockReturnValue(
      new Promise(() => {})
    );
    vi.mocked(clientApi.listGames).mockReturnValue(new Promise(() => {}));

    render(<GamesWorkspace />);
    expect(screen.getByText("Loading games...")).toBeInTheDocument();
  });
});
