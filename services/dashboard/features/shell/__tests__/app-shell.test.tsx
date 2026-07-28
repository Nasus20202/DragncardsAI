import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";

import { AppShell } from "@/features/shell/components/app-shell";

const themeState = vi.hoisted(() => ({
  resolvedTheme: "dark",
  setTheme: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    className,
  }: {
    href: string;
    children: React.ReactNode;
    className?: string;
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/swagger",
}));

vi.mock("@/features/shell/components/providers", () => ({
  useTheme: () => themeState,
}));

describe("AppShell", () => {
  it("renders nav links and toggles theme", async () => {
    render(
      <AppShell appName="DragncardsAI" bifrostUrl="http://localhost:4003">
        <div>Child content</div>
      </AppShell>
    );

    expect(screen.getByRole("link", { name: /logo/i })).toHaveAttribute(
      "href",
      "/play"
    );
    expect(screen.getByText("DragncardsAI")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Swagger" }).className).toContain(
      "bg-default-100"
    );
    expect(screen.getByText("Child content")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /toggle colour theme/i })
    );
    expect(themeState.setTheme).toHaveBeenCalledWith("light");
  });

  it("links to the Bifrost UI in a new tab", () => {
    render(
      <AppShell appName="DragncardsAI" bifrostUrl="http://bifrost.test:4003">
        <div>Child content</div>
      </AppShell>
    );

    const link = screen.getByRole("link", { name: /bifrost/i });
    expect(link).toHaveAttribute("href", "http://bifrost.test:4003");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    // Visually consistent with the internal nav entries.
    expect(link.className).toContain("text-default-500");
  });
});
