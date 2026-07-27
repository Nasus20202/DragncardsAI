import "@testing-library/jest-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ToggleInfoRow } from "@/features/play/components/toggle-info-row";

// Faithful HeroUI 3 Switch mock: only `Switch.Content` renders the clickable
// label + hidden input; `Switch.Control`/`Switch.Thumb` are plain spans. This
// mirrors the real DOM so a control placed outside `Switch.Content` (its old,
// broken position) would not toggle — guarding the fix from regressing.
vi.mock("@heroui/react", async () => {
  const React = await import("react");

  type ChildrenProps = { children?: React.ReactNode; className?: string };
  type SwitchRootProps = ChildrenProps & {
    "aria-label"?: string;
    onChange?: (value: boolean) => void;
    isSelected?: boolean;
  };

  const SwitchContext = React.createContext<{
    ariaLabel?: string;
    onChange?: (value: boolean) => void;
    isSelected?: boolean;
  }>({});

  const Switch = Object.assign(
    ({ children, onChange, isSelected, ...props }: SwitchRootProps) => (
      <div>
        <SwitchContext.Provider
          value={{
            ariaLabel: props["aria-label"],
            onChange,
            isSelected,
          }}
        >
          {children}
        </SwitchContext.Provider>
      </div>
    ),
    {
      // The clickable label; clicking any descendant toggles the input.
      Content: ({ children, className }: ChildrenProps) => {
        const { ariaLabel, onChange, isSelected } =
          React.useContext(SwitchContext);
        return (
          <label aria-label={ariaLabel} className={className}>
            <input
              aria-label={ariaLabel}
              checked={isSelected}
              type="checkbox"
              onChange={(event) => onChange?.(event.target.checked)}
            />
            {children}
          </label>
        );
      },
      Control: ({ children, className }: ChildrenProps) => (
        <span className={className} data-testid="switch-control">
          {children}
        </span>
      ),
      Thumb: () => <span data-testid="switch-thumb" />,
    }
  );

  return {
    Button: ({
      children,
      onPress,
      onClick,
      ariaLabel,
      className,
      isDisabled,
      ...props
    }: {
      children: React.ReactNode;
      onPress?: () => void;
      onClick?: React.MouseEventHandler<HTMLButtonElement>;
      /** Legacy alias — the real component uses the `aria-label` DOM prop. */
      ariaLabel?: string;
      "aria-label"?: string;
      className?: string;
      isDisabled?: boolean;
    }) => (
      <button
        aria-label={props["aria-label"] ?? ariaLabel}
        className={className}
        disabled={isDisabled}
        onClick={(event) => {
          onClick?.(event);
          onPress?.();
        }}
      >
        {children}
      </button>
    ),
    Switch,
    Tooltip: Object.assign(
      ({ children }: { children: React.ReactNode }) => <>{children}</>,
      {
        Trigger: ({ children }: { children: React.ReactNode }) => (
          <>{children}</>
        ),
        Content: ({ children }: { children: React.ReactNode }) => (
          <>{children}</>
        ),
      }
    ),
  };
});

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

  it("toggles when the control (not just the label text) is clicked", () => {
    const onChange = vi.fn();

    render(
      <ToggleInfoRow
        label="Reasoning stream"
        checked={true}
        onChange={onChange}
      />
    );

    // Clicking the visual toggle control must flip the switch. This regressed
    // when Switch.Control sat outside the clickable Switch.Content.
    fireEvent.click(screen.getByTestId("switch-control"));
    expect(onChange).toHaveBeenCalledWith(false);
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

    // The action button carries `aria-label`, so that is its accessible name.
    const button = screen.getByRole("button", { name: "Delete custom-mcp" });
    expect(button).toHaveTextContent("Delete");
    expect(button).toHaveClass("group-hover:opacity-100");

    fireEvent.click(button);
    expect(onPress).toHaveBeenCalledOnce();
  });
});
