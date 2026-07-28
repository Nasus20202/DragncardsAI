"use client";

import { ComboBox, Input, ListBox, ListBoxItem } from "@heroui/react";
import { useState } from "react";

export interface ComboSelectItem {
  value: string;
  label: string;
}

/**
 * Case-insensitive substring match used to narrow a {@link ComboSelect} list as
 * the user types. An empty query keeps the full list so opening the control
 * always shows every option.
 */
export function filterComboSelectItems(
  items: ComboSelectItem[],
  query: string
): ComboSelectItem[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return items;
  return items.filter((item) => item.label.toLowerCase().includes(needle));
}

/**
 * Searchable single-value picker: a HeroUI `ComboBox` whose text input filters
 * the option list, for lists too long to scan in a plain `Select` (model
 * catalogs, in particular). Selection is committed only when an option is
 * chosen; typing without choosing leaves `value` untouched and the input snaps
 * back to the committed label when the popover closes.
 *
 * Used by the Play settings panel and by the History tab's judge configuration.
 */
export function ComboSelect({
  label,
  items,
  value,
  disabled,
  inputId,
  inputTestId,
  onChange,
}: {
  /** Accessible name for the control. */
  label: string;
  items: ComboSelectItem[];
  value: string;
  disabled?: boolean;
  inputId?: string;
  inputTestId?: string;
  onChange: (value: string) => void;
}) {
  // `null` means "not searching": the field mirrors the committed value. Holding
  // the query in its own state instead of mirroring `value` into state keeps an
  // unrelated re-render of the owning panel — which hands down a fresh `items`
  // array every time — from wiping what the user has typed.
  const [query, setQuery] = useState<string | null>(null);

  const committedLabel = items.find((i) => i.value === value)?.label ?? value;
  const inputValue = query ?? committedLabel;
  const filtered =
    query === null ? items : filterComboSelectItems(items, query);

  return (
    <ComboBox
      fullWidth
      aria-label={label}
      isDisabled={disabled}
      value={value}
      inputValue={inputValue}
      onInputChange={setQuery}
      onOpenChange={(isOpen) => {
        // Opening blanks the field so the whole list is offered; closing without
        // a selection drops back to the committed value's label.
        setQuery(isOpen ? "" : null);
      }}
      onChange={(nextValue) => {
        if (nextValue) {
          setQuery(null);
          onChange(String(nextValue));
        }
      }}
    >
      <ComboBox.InputGroup>
        <Input aria-label={label} data-testid={inputTestId} id={inputId} />
        <ComboBox.Trigger />
      </ComboBox.InputGroup>
      <ComboBox.Popover>
        <ListBox aria-label={label}>
          {filtered.map((item) => (
            <ListBoxItem
              key={item.value}
              id={item.value}
              textValue={item.label}
            >
              {item.label}
            </ListBoxItem>
          ))}
        </ListBox>
      </ComboBox.Popover>
    </ComboBox>
  );
}
