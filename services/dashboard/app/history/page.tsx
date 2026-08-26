import { HistoryWorkspace } from "@/features/history/components/history-workspace";
import { GamePlatform } from "@/features/shared/lib/types";

export default async function HistoryPage({
  searchParams,
}: {
  searchParams: Promise<{ game_id?: string; platform?: GamePlatform }>;
}) {
  const { game_id, platform } = await searchParams;
  return (
    <HistoryWorkspace
      initialGameId={game_id ?? null}
      initialPlatform={platform}
    />
  );
}
