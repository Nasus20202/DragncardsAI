import { ProviderResponse } from "@/features/shared/lib/types";

const SESSION_QUERY_PARAM = "session";

export function readSelectedSessionIdFromUrl(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  const params = new URLSearchParams(window.location.search);
  return params.get(SESSION_QUERY_PARAM);
}

export function writeSelectedSessionIdToUrl(id: string | null) {
  if (typeof window === "undefined") {
    return;
  }

  const url = new URL(window.location.href);
  if (id) {
    url.searchParams.set(SESSION_QUERY_PARAM, id);
  } else {
    url.searchParams.delete(SESSION_QUERY_PARAM);
  }
  window.history.replaceState({}, "", url);
}

export function dedupeProviders(providers: ProviderResponse[]) {
  const byId = new Map<string, ProviderResponse>();
  for (const provider of providers) {
    if (!byId.has(provider.provider_id)) {
      byId.set(provider.provider_id, provider);
    }
  }
  return Array.from(byId.values());
}

export function subscribeToMobileLayout(onStoreChange: () => void) {
  if (typeof window === "undefined") {
    return () => {};
  }

  const mediaQuery = window.matchMedia("(max-width: 767px)");
  mediaQuery.addEventListener("change", onStoreChange);

  return () => {
    mediaQuery.removeEventListener("change", onStoreChange);
  };
}

export function getMobileLayoutSnapshot() {
  if (typeof window === "undefined") {
    return false;
  }

  return window.matchMedia("(max-width: 767px)").matches;
}
