import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import { SwaggerWorkspace } from "@/features/swagger/components/swagger-workspace";

vi.mock("@heroui/react", () => ({
  Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Chip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Spinner: () => <div>Spinner</div>,
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SwaggerWorkspace", () => {
  it("shows loading then renders the iframe and partial-load warning", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ document: { openapi: "3.1.0" }, errors: [{ service: "game", message: "offline" }] }),
    }));

    render(<SwaggerWorkspace />);

    expect(screen.getByText("Loading merged OpenAPI")).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText("Swagger playground")).toBeInTheDocument());
    expect(screen.getByText("Partial OpenAPI load:")).toBeInTheDocument();
    expect(screen.getByText("game: offline")).toBeInTheDocument();
    expect(screen.getByTitle("Swagger UI")).toHaveAttribute("src", "/swagger/embed");
  });

  it("shows a fetch error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
    }));

    render(<SwaggerWorkspace />);

    await waitFor(() => expect(screen.getByText("Failed to load merged OpenAPI: 503")).toBeInTheDocument());
  });
});
