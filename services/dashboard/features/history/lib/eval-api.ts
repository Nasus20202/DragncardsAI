import { readJson } from "@/features/history/lib/http";
import {
  EvaluationCancelResponse,
  EvaluationClearResponse,
  EvaluationQueueListResponse,
  EvaluationRequestAck,
  EvaluationRequestBody,
  EvaluationRequestStatusResponse,
  EvaluationRound,
  EvaluationRoundsResponse,
} from "@/features/shared/lib/types";

/**
 * The rounds the eval-service detects for a game, so the user can pick a ROUND
 * to evaluate instead of picking a move inside one.
 *
 * Deliberately server-sourced rather than re-derived from the timeline: round
 * boundaries are the eval-service's own detection, so a round offered here is a
 * round it can actually grade, and the two cannot drift apart.
 * Calls `GET /api/proxy/eval/games/{gameId}/rounds`.
 */
export async function listGameRounds(
  gameId: string
): Promise<EvaluationRound[]> {
  const response = await fetch(
    `/api/proxy/eval/games/${encodeURIComponent(gameId)}/rounds`,
    { cache: "no-store" }
  );
  const body = await readJson<EvaluationRoundsResponse>(response);
  return body.rounds ?? [];
}

/**
 * List in-progress and recent evaluation requests across all games (newest
 * first). Calls the cross-game `GET /api/proxy/eval/evaluations`.
 *
 * @param active When true, only requests with at least one non-terminal target.
 * @param limit  Bounded number of requests to return.
 */
export async function listEvaluations(options?: {
  active?: boolean;
  limit?: number;
}): Promise<EvaluationQueueListResponse> {
  const params = new URLSearchParams();
  if (options?.active) params.set("active", "true");
  if (options?.limit !== undefined) params.set("limit", String(options.limit));
  const query = params.toString();
  const response = await fetch(
    `/api/proxy/eval/evaluations${query ? `?${query}` : ""}`,
    { cache: "no-store" }
  );
  return readJson<EvaluationQueueListResponse>(response);
}

/**
 * Submit an on-demand evaluation request for selected targets of a game.
 * Calls `POST /api/proxy/eval/games/{gameId}/evaluations`.
 */
export async function requestEvaluation(
  gameId: string,
  body: EvaluationRequestBody
): Promise<EvaluationRequestAck> {
  const response = await fetch(
    `/api/proxy/eval/games/${encodeURIComponent(gameId)}/evaluations`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }
  );
  return readJson<EvaluationRequestAck>(response);
}

/**
 * Poll the per-target status/results of a previously submitted request.
 * Calls `GET /api/proxy/eval/games/{gameId}/evaluations/{requestId}`.
 */
export async function getEvaluationRequest(
  gameId: string,
  requestId: string
): Promise<EvaluationRequestStatusResponse> {
  const response = await fetch(
    `/api/proxy/eval/games/${encodeURIComponent(gameId)}/evaluations/${encodeURIComponent(
      requestId
    )}`,
    { cache: "no-store" }
  );
  return readJson<EvaluationRequestStatusResponse>(response);
}

/**
 * Request cancellation of an in-flight evaluation. Marks all non-terminal
 * targets `cancelled` and aborts any in-flight judge calls.
 * Calls `POST /api/proxy/eval/games/{gameId}/evaluations/{requestId}/cancel`.
 */
export async function cancelEvaluation(
  gameId: string,
  requestId: string
): Promise<EvaluationCancelResponse> {
  const response = await fetch(
    `/api/proxy/eval/games/${encodeURIComponent(gameId)}/evaluations/${encodeURIComponent(
      requestId
    )}/cancel`,
    { method: "POST" }
  );
  return readJson<EvaluationCancelResponse>(response);
}

/**
 * Delete a single fully-terminal evaluation request from the persistent queue.
 * The eval-service rejects clearing a request that still has a non-terminal
 * target with HTTP 409 (cancel it first). Recorded history verdicts are not
 * affected — this only removes the queue tracking rows.
 * Calls `DELETE /api/proxy/eval/evaluations/{requestId}` (204 on success).
 */
export async function deleteEvaluation(requestId: string): Promise<void> {
  const response = await fetch(
    `/api/proxy/eval/evaluations/${encodeURIComponent(requestId)}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(
      body?.detail ?? `${response.status} ${response.statusText}`
    );
  }
}

/**
 * Clear every fully-terminal evaluation request from the persistent queue.
 * Requests still pending/running are left intact. Recorded history verdicts are
 * not affected. Calls `POST /api/proxy/eval/evaluations/clear`.
 */
export async function clearEvaluations(): Promise<EvaluationClearResponse> {
  const response = await fetch("/api/proxy/eval/evaluations/clear", {
    method: "POST",
  });
  return readJson<EvaluationClearResponse>(response);
}
