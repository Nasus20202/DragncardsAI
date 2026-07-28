import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  readLastUsedDraft,
  writeLastUsedDraft,
} from "@/features/play/lib/last-used-draft";
import { SessionDraft } from "@/features/shared/lib/types";

const STORAGE_KEY = "play:lastUsedDraft";

const draft: SessionDraft = {
  name: "A session name",
  providerId: "anthropic",
  modelName: "claude-3-5",
  recentMessageLimit: "12",
  recentToolExchangeLimit: "5",
  reasoning: { enabled: true, effort: "high", maxTokens: "2048" },
  gatewayOptionsText: '{"temperature":0.3}',
  providerOptionsText: '{"foo":"bar"}',
  selectedSkills: ["skill-a", "skill-b"],
};

function installStorage() {
  const store = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: vi.fn((key: string) => store.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => {
        store.set(key, value);
      }),
      removeItem: vi.fn((key: string) => {
        store.delete(key);
      }),
      clear: vi.fn(() => store.clear()),
    },
  });
  return store;
}

describe("last-used draft storage", () => {
  let store: Map<string, string>;

  beforeEach(() => {
    store = installStorage();
  });

  it("returns null when nothing has been stored", () => {
    expect(readLastUsedDraft()).toBeNull();
  });

  it("round-trips every configuration field except the session name", () => {
    writeLastUsedDraft(draft);

    const restored = readLastUsedDraft();

    expect(restored).toEqual({ ...draft, name: "" });
  });

  it("does not alias the stored arrays and objects", () => {
    writeLastUsedDraft(draft);

    const restored = readLastUsedDraft();
    restored?.selectedSkills.push("skill-c");

    expect(readLastUsedDraft()?.selectedSkills).toEqual(["skill-a", "skill-b"]);
  });

  it("rejects a payload that is not valid JSON", () => {
    store.set(STORAGE_KEY, "{not json");

    expect(readLastUsedDraft()).toBeNull();
  });

  it.each([
    ["a missing provider", { ...draft, providerId: undefined }],
    ["a non-string model", { ...draft, modelName: 42 }],
    ["a malformed reasoning block", { ...draft, reasoning: { enabled: true } }],
    ["a non-string skill entry", { ...draft, selectedSkills: ["ok", 7] }],
    [
      "an unexpected reasoning effort",
      {
        ...draft,
        reasoning: { ...draft.reasoning, effort: "extreme" },
      },
    ],
  ])("rejects a stored draft with %s", (_label, payload) => {
    store.set(STORAGE_KEY, JSON.stringify(payload));

    expect(readLastUsedDraft()).toBeNull();
  });

  it("survives storage that refuses to be written", () => {
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: {
        getItem: vi.fn(() => {
          throw new Error("blocked");
        }),
        setItem: vi.fn(() => {
          throw new Error("quota exceeded");
        }),
        removeItem: vi.fn(),
      },
    });

    expect(() => writeLastUsedDraft(draft)).not.toThrow();
    expect(readLastUsedDraft()).toBeNull();
  });
});
