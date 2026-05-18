import "@testing-library/jest-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ToggleInfoRow } from "@/features/play/components/toggle-info-row";

type MockChildrenProps = {
  children?: React.ReactNode;
};

type MockSwitchRootProps = MockChildrenProps & {
  ariaLabel?: string;
  onChange?: (value: boolean) => void;
  isSelected?: boolean;
};

type MockClassNameChildrenProps = MockChildrenProps & {
  className?: string;
};

vi.mock("@heroui/react", () => ({
  Button: ({
    children,
    onPress,
    ariaLabel,
    className,
    isDisabled,
  }: {
    children: React.ReactNode;
    onPress?: () => void;
    ariaLabel?: string;
    className?: string;
    isDisabled?: boolean;
  }) => (
    <button
      aria-label={ariaLabel}
      className={className}
      disabled={isDisabled}
      onClick={onPress}
    >
      {children}
    </button>
  ),
  Switch: Object.assign(
    ({ children, ariaLabel, onChange, isSelected }: MockSwitchRootProps) => (
      <label aria-label={ariaLabel}>
        <input
          aria-label={ariaLabel}
          checked={isSelected}
          type="checkbox"
          onChange={(event) => onChange?.(event.target.checked)}
        />
        {children}
      </label>
    ),
    {
      Content: ({ children, className }: MockClassNameChildrenProps) => (
        <div className={className}>{children}</div>
      ),
      Control: ({ children, className }: MockClassNameChildrenProps) => (
        <div className={className}>{children}</div>
      ),
      Thumb: () => <div />,
    }
  ),
  Tooltip: Object.assign(
    ({ children }: { children: React.ReactNode }) => <>{children}</>,
    {
      Trigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
      Content: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    }
  ),
}));

describe("ToggleInfoRow", () => {
  it("renders info trigger content when provided", () => {
    render(
      <ToggleInfoRow
        label="game-service"
        checked={true}
        onChange={vi.fn()}
        infoLabel="Info about game-service"
        infoContent={<div>Transport: streamable-http</div>}
      />
    );

    expect(
      screen.getByRole("button", { name: "Info about game-service" })
    ).toBeInTheDocument();
    expect(screen.getByText("Transport: streamable-http")).toBeInTheDocument();
  });

  it("renders row action beside the label and calls it", () => {
    const onPress = vi.fn();

    render(
      <ToggleInfoRow
        label="custom-mcp"
        checked={false}
        onChange={vi.fn()}
        action={{
          label: "Delete",
          ariaLabel: "Delete custom-mcp",
          onPress,
        }}
        actionVisibility="hover"
      />
    );

    const button = screen.getByRole("button", { name: "Delete" });
    expect(button).toBeInTheDocument();
    expect(button).toHaveClass("group-hover:opacity-100");

    fireEvent.click(button);
    expect(onPress).toHaveBeenCalledOnce();
  });
});
