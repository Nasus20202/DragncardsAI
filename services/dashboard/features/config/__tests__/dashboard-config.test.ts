import { readFileSync } from "node:fs";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { getPublicConfig } from "@/features/config/lib/dashboard-config";
import { DASHBOARD_CONFIG_ENV_VARS } from "@/vitest.setup";

afterEach(() => {
  delete process.env.BIFROST_UI_URL;
});

describe("dashboard config", () => {
  it("falls back to the local Bifrost UI port", () => {
    delete process.env.BIFROST_UI_URL;
    expect(getPublicConfig().bifrostUiUrl).toBe("http://localhost:4003");
  });

  it("uses BIFROST_UI_URL when set", () => {
    process.env.BIFROST_UI_URL = "https://gateway.example/ui";
    expect(getPublicConfig().bifrostUiUrl).toBe("https://gateway.example/ui");
  });

  // The test setup clears these before every test so no suite silently inherits
  // a developer's exported stack configuration (service urls, default provider
  // and model, default skills). If a new variable is read here but not cleared,
  // that isolation quietly stops covering it - so fail loudly instead.
  it("clears every configuration variable it reads during tests", () => {
    const source = readFileSync(
      path.resolve(__dirname, "../lib/dashboard-config.ts"),
      "utf8"
    );
    const read = new Set(
      [...source.matchAll(/process\.env\.([A-Z0-9_]+)/g)].map(
        (match) => match[1]
      )
    );
    expect(read.size).toBeGreaterThan(0);
    expect([...read].sort()).toEqual(
      [...read]
        .filter((name) =>
          (DASHBOARD_CONFIG_ENV_VARS as readonly string[]).includes(name)
        )
        .sort()
    );
  });
});
