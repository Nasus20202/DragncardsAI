import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import { ContextHealthWidget } from "@/features/play/components/context-health-widget";
import { ContextMetadata } from "@/features/shared/lib/types";

// Mock HeroUI components to avoid complex provider setup
vi.mock("@heroui/react", () => ({
  Button: ({
    children,
    isDisabled,
    onPress,
  }: {
    children: React.ReactNode;
    isDisabled?: boolean;
    onPress?: () => void;
  }) => (
    <button disabled={isDisabled} onClick={onPress}>
      {children}
    </button>
  ),
  ProgressBar: ({
    value,
    color,
    "aria-label": ariaLabel,
  }: {
    value: number;
    color: string;
    "aria-label": string;
  }) => (
    <div
      role="progressbar"
      aria-label={ariaLabel}
      data-value={value}
      data-color={color}
    />
  ),
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const baseMetadata: ContextMetadata = {
  tokens_used: 50000,
  context_window_size: 128000,
  usage_ratio: 0.39,
  compaction_count: 0,
  last_compacted_at: null,
  multi_turn_memory: true,
};

describe("ContextHealthWidget", () => {
  it("renders null when contextMetadata is null", () => {
    const { container } = render(
      <ContextHealthWidget
        contextMetadata={null}
        isBusy={false}
        onCompact={vi.fn()}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows progress bar with correct percentage (below 70%)", () => {
    render(
      <ContextHealthWidget
        contextMetadata={baseMetadata}
        isBusy={false}
        onCompact={vi.fn()}
      />
    );
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("data-value", "39");
    expect(bar).toHaveAttribute("data-color", "default");
  });

  it("colors progress bar amber between 70% and 85%", () => {
    const metadata: ContextMetadata = {
      ...baseMetadata,
      usage_ratio: 0.75,
      tokens_used: 96000,
    };
    render(
      <ContextHealthWidget
        contextMetadata={metadata}
        isBusy={false}
        onCompact={vi.fn()}
      />
    );
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("data-color", "warning");
  });

  it("colors progress bar red above 85%", () => {
    const metadata: ContextMetadata = {
      ...baseMetadata,
      usage_ratio: 0.9,
      tokens_used: 115200,
    };
    render(
      <ContextHealthWidget
        contextMetadata={metadata}
        isBusy={false}
        onCompact={vi.fn()}
      />
    );
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("data-color", "danger");
  });

  it("shows Memory off state and no progress bar when multi_turn_memory is false", () => {
    const metadata: ContextMetadata = {
      ...baseMetadata,
      multi_turn_memory: false,
    };
    render(
      <ContextHealthWidget
        contextMetadata={metadata}
        isBusy={false}
        onCompact={vi.fn()}
      />
    );
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.getByText("Memory off")).toBeInTheDocument();
  });

  it("disables Compact button while busy", () => {
    render(
      <ContextHealthWidget
        contextMetadata={baseMetadata}
        isBusy={true}
        onCompact={vi.fn()}
      />
    );
    const button = screen.getByRole("button", { name: /compact/i });
    expect(button).toBeDisabled();
  });

  it("calls onCompact when Compact button is clicked", () => {
    const onCompact = vi.fn();
    render(
      <ContextHealthWidget
        contextMetadata={baseMetadata}
        isBusy={false}
        onCompact={onCompact}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /compact/i }));
    expect(onCompact).toHaveBeenCalledOnce();
  });

  it("hides Compact button when multi_turn_memory is false", () => {
    const metadata: ContextMetadata = {
      ...baseMetadata,
      multi_turn_memory: false,
    };
    render(
      <ContextHealthWidget
        contextMetadata={metadata}
        isBusy={false}
        onCompact={vi.fn()}
      />
    );
    expect(screen.queryByRole("button", { name: /compact/i })).toBeNull();
  });

  it("shows compaction count in summary", () => {
    const metadata: ContextMetadata = { ...baseMetadata, compaction_count: 3 };
    render(
      <ContextHealthWidget
        contextMetadata={metadata}
        isBusy={false}
        onCompact={vi.fn()}
      />
    );
    expect(screen.getByText(/3 compactions/i)).toBeInTheDocument();
  });
});
