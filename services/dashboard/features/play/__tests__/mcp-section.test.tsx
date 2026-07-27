import "@testing-library/jest-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { McpSection } from "@/features/play/components/mcp-section";

type MockChildrenProps = {
  children?: React.ReactNode;
};

type MockButtonProps = MockChildrenProps & {
  onPress?: () => void;
  onClick?: React.MouseEventHandler<HTMLButtonElement>;
  /** Legacy alias — the real component uses the `aria-label` DOM prop. */
  ariaLabel?: string;
  "aria-label"?: string;
  className?: string;
  isDisabled?: boolean;
};

type MockInputProps = {
  value?: string;
  onChange?: React.ChangeEventHandler<HTMLInputElement>;
  ariaLabel?: string;
  placeholder?: string;
};

type MockModalCloseTriggerProps = {
  ariaLabel?: string;
};

type MockSwitchRootProps = MockChildrenProps & {
  ariaLabel?: string;
  onChange?: (value: boolean) => void;
  isSelected?: boolean;
  isDisabled?: boolean;
};

type MockClassNameChildrenProps = MockChildrenProps & {
  className?: string;
};

vi.mock("@heroui/react", () => ({
  Button: ({
    children,
    onPress,
    onClick,
    ariaLabel,
    className,
    isDisabled,
    ...props
  }: MockButtonProps) => (
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
  Input: ({ value, onChange, ariaLabel, placeholder }: MockInputProps) => (
    <input
      aria-label={ariaLabel}
      placeholder={placeholder}
      value={value}
      onChange={onChange}
    />
  ),
  ListBox: ({ children }: MockChildrenProps) => <div>{children}</div>,
  ListBoxItem: ({ children }: MockChildrenProps) => <div>{children}</div>,
  Modal: Object.assign(({ children }: MockChildrenProps) => <>{children}</>, {
    Backdrop: ({ children }: MockChildrenProps) => <>{children}</>,
    Container: ({ children }: MockChildrenProps) => <>{children}</>,
    Dialog: ({ children }: MockChildrenProps) => <>{children}</>,
  }),
  ModalBody: ({ children }: MockChildrenProps) => <div>{children}</div>,
  ModalCloseTrigger: ({ ariaLabel }: MockModalCloseTriggerProps) => (
    <button aria-label={ariaLabel} />
  ),
  ModalFooter: ({ children }: MockChildrenProps) => <div>{children}</div>,
  ModalHeader: ({ children }: MockChildrenProps) => <div>{children}</div>,
  ModalHeading: ({ children }: MockChildrenProps) => <div>{children}</div>,
  Select: Object.assign(
    ({ children }: MockChildrenProps) => <div>{children}</div>,
    {
      Trigger: ({ children }: MockChildrenProps) => <div>{children}</div>,
      Value: () => <div />,
      Indicator: () => <div />,
      Popover: ({ children }: MockChildrenProps) => <div>{children}</div>,
    }
  ),
  TextField: ({ children }: MockChildrenProps) => <div>{children}</div>,
  Tooltip: Object.assign(({ children }: MockChildrenProps) => <>{children}</>, {
    Trigger: ({ children }: MockChildrenProps) => <>{children}</>,
    Content: ({ children }: MockChildrenProps) => <>{children}</>,
  }),
  Switch: Object.assign(
    ({
      children,
      ariaLabel,
      onChange,
      isSelected,
      isDisabled,
    }: MockSwitchRootProps) => (
      <label aria-label={ariaLabel}>
        <input
          aria-label={ariaLabel}
          checked={isSelected}
          disabled={isDisabled}
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
}));

describe("McpSection", () => {
  it("shows disabled custom MCPs and renders delete action plus info trigger", () => {
    const onDelete = vi.fn();

    render(
      <McpSection
        mcps={[
          {
            name: "custom-mcp",
            transport: "streamable-http",
            server_url: "http://custom/mcp/",
            enabled: false,
            custom: true,
          },
        ]}
        isBusy={false}
        onToggle={vi.fn().mockResolvedValue(undefined)}
        onAdd={vi.fn().mockResolvedValue(undefined)}
        onDelete={onDelete}
      />
    );

    expect(screen.getByText("custom-mcp")).toBeInTheDocument();
    expect(screen.getByText("Custom MCP")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Info about custom-mcp" })
    ).toBeInTheDocument();
    expect(screen.getByText("streamable-http")).toBeInTheDocument();

    // The action button carries `aria-label`, so that is its accessible name.
    const deleteButton = screen.getByRole("button", {
      name: "Delete custom-mcp",
    });
    expect(deleteButton).toHaveTextContent("Delete");
    expect(deleteButton).toHaveClass("group-hover:opacity-100");

    fireEvent.click(deleteButton);
    expect(onDelete).toHaveBeenCalledWith("custom-mcp");
  });
});
