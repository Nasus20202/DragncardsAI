import { Button, Switch, Tooltip } from "@heroui/react";
import { ReactNode } from "react";

export function ToggleInfoRow({
  label,
  description,
  checked,
  disabled,
  onChange,
  infoLabel,
  infoContent,
  tooltipPlacement = "left",
  action,
  actionVisibility = "always",
}: {
  label: string;
  description?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
  infoLabel?: string;
  infoContent?: ReactNode;
  tooltipPlacement?: "top" | "bottom" | "left" | "right";
  action?: {
    label: string;
    ariaLabel: string;
    onPress: () => void;
    disabled?: boolean;
    variant?:
      | "ghost"
      | "primary"
      | "secondary"
      | "tertiary"
      | "outline"
      | "danger"
      | "danger-soft";
  };
  actionVisibility?: "always" | "hover";
}) {
  const actionClassName =
    actionVisibility === "hover"
      ? "pointer-events-none opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100"
      : undefined;

  return (
    <div className="group flex items-center gap-1">
      <div className="flex-1">
        <Switch
          aria-label={label}
          isSelected={checked}
          isDisabled={disabled}
          onChange={onChange}
          className="w-full py-0.5"
        >
          {/* Switch.Content is the clickable SwitchButton; it must wrap the
              control so clicking the toggle itself (not just the label) works. */}
          <Switch.Content className="flex w-full items-center justify-between gap-3">
            <div className="flex flex-1 flex-col justify-center">
              <div className="flex items-center gap-2 leading-none">
                <div className="text-sm text-foreground">{label}</div>
                {action ? (
                  <Button
                    size="sm"
                    variant={action.variant ?? "danger-soft"}
                    aria-label={action.ariaLabel}
                    isDisabled={action.disabled}
                    onPress={action.onPress}
                    className={
                      actionClassName
                        ? `${actionClassName} h-6 min-h-6 self-center px-2`
                        : "h-6 min-h-6 self-center px-2"
                    }
                  >
                    {action.label}
                  </Button>
                ) : null}
              </div>
              {description && (
                <div className="text-xs text-default-400">{description}</div>
              )}
            </div>
            <Switch.Control className="shrink-0">
              <Switch.Thumb />
            </Switch.Control>
          </Switch.Content>
        </Switch>
      </div>
      {infoContent && infoLabel ? (
        <Tooltip delay={200} closeDelay={250}>
          <Tooltip.Trigger>
            <Button
              isIconOnly
              size="sm"
              variant="ghost"
              className="h-auto min-h-0 shrink-0 cursor-default select-none bg-transparent px-0 text-xs text-default-300 hover:text-default-500 focus:outline-none"
              aria-label={infoLabel}
              onClick={(event) => event.preventDefault()}
            >
              ⓘ
            </Button>
          </Tooltip.Trigger>
          <Tooltip.Content placement={tooltipPlacement} className="max-w-sm">
            {infoContent}
          </Tooltip.Content>
        </Tooltip>
      ) : null}
    </div>
  );
}
