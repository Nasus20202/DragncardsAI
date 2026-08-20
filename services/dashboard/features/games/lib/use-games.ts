"use client";

import { GameSession } from "@/features/shared/lib/types";
import {
  fetchDashboardConfig,
  listGames,
} from "@/features/play/lib/client-api";
import { useEffect, useState } from "react";

export function useGames() {
  const [games, setGames] = useState<GameSession[]>([]);
  const [selectedGameId, setSelectedGameId] = useState<string | null>(null);
  const [frontendUrl, setFrontendUrl] = useState<string>("");
  const [marvelLcgBaseUrl, setMarvelLcgBaseUrl] = useState<string>("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadConfig = async () => {
      try {
        const config = await fetchDashboardConfig();
        setFrontendUrl(config.dragncardsFrontendUrl);
        setMarvelLcgBaseUrl(config.marvelLcgBaseUrl ?? "");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load config");
      }
    };
    loadConfig();
  }, []);

  useEffect(() => {
    const loadGames = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const gamesList = await listGames();
        setGames(gamesList ?? []);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load games");
      } finally {
        setIsLoading(false);
      }
    };
    loadGames();
  }, []);

  const selectedGame = games?.find((g) => g.id === selectedGameId);

  return {
    games: games ?? [],
    selectedGame,
    frontendUrl,
    marvelLcgBaseUrl,
    error,
    isLoading,
    selectGame: setSelectedGameId,
  };
}
