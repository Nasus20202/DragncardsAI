/**
 * Parse a `fetch` Response as JSON, throwing a descriptive Error on a non-ok
 * status. Shared by the history and eval API clients.
 */
export async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(
      body?.detail ?? `${response.status} ${response.statusText}`
    );
  }

  return (await response.json()) as T;
}
