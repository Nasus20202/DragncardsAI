/**
 * The URL of a DragnCards room, given the frontend base URL and a room slug.
 *
 * The routing shape (`/room/<slug>`) and the decision to percent-encode the slug
 * rather than trust it live here once. Two surfaces need it — the embedded board
 * viewer and the link a branch restore offers to the game it created — and a
 * second copy of the template literal means a routing change silently fixes one
 * of them.
 */
export function dragncardsRoomUrl(
  frontendUrl: string,
  roomSlug: string
): string {
  return `${frontendUrl}/room/${encodeURIComponent(roomSlug)}`;
}
