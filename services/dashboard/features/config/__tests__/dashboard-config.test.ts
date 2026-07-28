import { afterEach, describe, expect, it } from "vitest";

import { getPublicConfig } from "@/features/config/lib/dashboard-config";

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
});
