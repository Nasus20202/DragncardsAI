/**
 * Parse a `fetch` Response as JSON, throwing a descriptive Error on a non-ok
 * status. Shared by the history and eval API clients.
 */

/** One entry of FastAPI's request-validation `detail` array. */
interface ValidationDetail {
  loc?: (string | number)[];
  msg?: string;
}

/**
 * FastAPI reports two different `detail` shapes: a plain string for an explicit
 * `HTTPException`, and an ARRAY of `{loc, msg}` objects for a 422 raised by
 * request-body validation. Interpolating the array yields `[object Object]`,
 * which is what the user used to see whenever a schema limit was hit — for
 * instance selecting more than the eight judge skill references the server
 * accepts, which is one screen away for a skill shipping 21 of them.
 */
function describeDetail(detail: unknown): string | null {
  if (typeof detail === "string" && detail) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((entry: ValidationDetail) => {
        if (!entry || typeof entry !== "object") return null;
        const msg = typeof entry.msg === "string" ? entry.msg : null;
        if (!msg) return null;
        // Drop the leading "body"/"query" frame; it names the request part, not
        // the field the user touched.
        const loc = (entry.loc ?? [])
          .filter((part) => part !== "body" && part !== "query")
          .join(".");
        return loc ? `${loc}: ${msg}` : msg;
      })
      .filter((part): part is string => Boolean(part));
    if (parts.length > 0) {
      return parts.join("; ");
    }
  }
  return null;
}

export async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: unknown;
    } | null;
    throw new Error(
      describeDetail(body?.detail) ??
        `${response.status} ${response.statusText}`
    );
  }

  return (await response.json()) as T;
}
