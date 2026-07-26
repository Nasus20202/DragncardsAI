import { HistoryWorkspace } from "@/features/history/components/history-workspace";

export default async function HistoryPage({
  searchParams,
}: {
  searchParams: Promise<{ game_id?: string }>;
}) {
  const { game_id } = await searchParams;
  return <HistoryWorkspace initialGameId={game_id ?? null} />;
}
