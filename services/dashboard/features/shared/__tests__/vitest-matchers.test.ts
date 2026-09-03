import { describe, expect, it } from "vitest";

describe("Vitest test setup", () => {
  it("registers Testing Library DOM matchers for every test", () => {
    expect(document.body).toBeInTheDocument();
  });
});
