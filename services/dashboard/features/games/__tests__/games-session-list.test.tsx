import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { describe, expect, it, vi } from "vitest";

import { GamesSessionList } from "@/features/games/components/games-session-list";
import { GameSession } from "@/features/shared/lib/types";

describe("GamesSessionList", () => {
  it("renders empty state when no games", () => {
    render(
      <GamesSessionList games={[]} selectedGameId={null} onSelect={vi.fn()} />
    );

    expect(screen.getByText("No active games")).toBeInTheDocument();
  });

  it("renders game list with correct data", () => {
    const games: GameSession[] = [
      {
        id: "game-123",
        plugin: "marvel-champions",
        plugin_id: 1,
        created_at: "2026-05-18T00:00:00Z",
        room_slug: "lively-fog-1234",
      },
      {
        id: "game-456",
        plugin: "swwitch",
        plugin_id: 2,
        created_at: "2026-05-18T00:00:00Z",
        room_slug: "calm-river-5678",
      },
    ];

    render(
      <GamesSessionList
        games={games}
        selectedGameId={null}
        onSelect={vi.fn()}
      />
    );

    expect(screen.getByText("lively-fog-1234")).toBeInTheDocument();
    expect(screen.getByText("marvel-champions")).toBeInTheDocument();
    expect(screen.getByText("calm-river-5678")).toBeInTheDocument();
    expect(screen.getByText("swwitch")).toBeInTheDocument();
  });

  it("calls onSelect when game is clicked", () => {
    const games: GameSession[] = [
      {
        id: "game-123",
        plugin: "marvel-champions",
        plugin_id: 1,
        created_at: "2026-05-18T00:00:00Z",
        room_slug: "lively-fog-1234",
      },
    ];
    const onSelect = vi.fn();

    render(
      <GamesSessionList
        games={games}
        selectedGameId={null}
        onSelect={onSelect}
      />
    );

    fireEvent.click(screen.getByTestId("game-session-game-123"));
    expect(onSelect).toHaveBeenCalledWith("game-123");
  });

  it("shows selected state for active game", () => {
    const games: GameSession[] = [
      {
        id: "game-123",
        plugin: "marvel-champions",
        plugin_id: 1,
        created_at: "2026-05-18T00:00:00Z",
        room_slug: "lively-fog-1234",
      },
    ];

    render(
      <GamesSessionList
        games={games}
        selectedGameId="game-123"
        onSelect={vi.fn()}
      />
    );

    const button = screen.getByTestId("game-session-game-123");
    expect(button).toBeInTheDocument();
    expect(button).toHaveTextContent("lively-fog-1234");
  });
});
