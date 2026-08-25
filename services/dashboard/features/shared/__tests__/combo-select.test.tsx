import "@testing-library/jest-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";

import {
  ComboSelect,
  filterComboSelectItems,
} from "@/features/shared/components/combo-select";
import { SelectField } from "@/features/shared/components/form-fields";
import { installResizeObserver } from "@/features/shared/__tests__/heroui-test-env";

const MODELS = [
  "anthropic/claude-sonnet-4",
  "anthropic/claude-haiku-4",
  "openai/gpt-5",
  "openai/gpt-5-mini",
];

const items = MODELS.map((model) => ({ value: model, label: model }));
const duplicateItems = [
  { value: "duplicate", label: "First label" },
  { value: "duplicate", label: "Second label" },
  { value: "unique", label: "Unique label" },
];

beforeAll(installResizeObserver);

describe("filterComboSelectItems", () => {
  it("keeps every item for an empty or whitespace query", () => {
    expect(filterComboSelectItems(items, "")).toHaveLength(4);
    expect(filterComboSelectItems(items, "   ")).toHaveLength(4);
  });

  it("matches substrings case-insensitively", () => {
    expect(filterComboSelectItems(items, "HAIKU").map((i) => i.value)).toEqual([
      "anthropic/claude-haiku-4",
    ]);
    expect(filterComboSelectItems(items, "gpt-5").map((i) => i.value)).toEqual([
      "openai/gpt-5",
      "openai/gpt-5-mini",
    ]);
  });

  it("returns nothing when no label matches", () => {
    expect(filterComboSelectItems(items, "llama")).toEqual([]);
  });
});

describe("ComboSelect", () => {
  it("renders duplicate values without React key or accessible id warnings", async () => {
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const user = userEvent.setup();
    const onComboChange = vi.fn();

    render(
      <>
        <SelectField
          id="provider"
          label="Provider"
          items={duplicateItems}
          value="duplicate"
          triggerTestId="provider-trigger"
          onChange={vi.fn()}
        />
        <ComboSelect
          label="Model"
          items={duplicateItems}
          value="unique"
          inputTestId="model-input"
          onChange={onComboChange}
        />
      </>
    );

    await user.click(screen.getByTestId("provider-trigger"));
    const providerOptions = screen.getAllByRole("option");
    expect(providerOptions).toHaveLength(2);
    expect(new Set(providerOptions.map((option) => option.id)).size).toBe(2);

    await user.click(screen.getByTestId("model-input"));
    const modelOptions = screen.getAllByRole("option");
    expect(modelOptions).toHaveLength(2);
    expect(new Set(modelOptions.map((option) => option.id)).size).toBe(2);
    await user.click(screen.getByRole("option", { name: "First label" }));
    expect(onComboChange).toHaveBeenCalledWith("duplicate");

    const duplicateKeyWarnings = consoleError.mock.calls.filter((call) =>
      call.some((argument) => String(argument).includes("same key"))
    );
    expect(duplicateKeyWarnings).toHaveLength(0);

    consoleError.mockRestore();
  });

  it("shows the committed value in the input", () => {
    render(
      <ComboSelect
        label="Judge model"
        items={items}
        value="openai/gpt-5"
        inputTestId="judge-model"
        onChange={vi.fn()}
      />
    );

    expect(screen.getByTestId("judge-model")).toHaveValue("openai/gpt-5");
  });

  it("filters the option list as the user types and commits the choice", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <ComboSelect
        label="Judge model"
        items={items}
        value="openai/gpt-5"
        inputTestId="judge-model"
        onChange={onChange}
      />
    );

    const input = screen.getByTestId("judge-model");
    await user.click(input);
    // Opening clears the input so the whole catalogue is offered.
    await waitFor(() =>
      expect(screen.getAllByRole("option")).toHaveLength(MODELS.length)
    );

    await user.keyboard("haiku");

    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(1));
    const option = screen.getByRole("option", {
      name: "anthropic/claude-haiku-4",
    });

    await user.click(option);

    expect(onChange).toHaveBeenCalledWith("anthropic/claude-haiku-4");
  });

  it("keeps the typed query when the owning panel re-renders", async () => {
    const user = userEvent.setup();
    // The owning panels rebuild `items` on every render, so a re-render that has
    // nothing to do with this control must not wipe what the user has typed.
    const picker = (props: { items: typeof items }) => (
      <ComboSelect
        label="Judge model"
        items={props.items}
        value="openai/gpt-5"
        inputTestId="judge-model"
        onChange={vi.fn()}
      />
    );

    const { rerender } = render(picker({ items }));

    await user.click(screen.getByTestId("judge-model"));
    await user.keyboard("haiku");
    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(1));

    rerender(picker({ items: MODELS.map((m) => ({ value: m, label: m })) }));

    expect(screen.getByTestId("judge-model")).toHaveValue("haiku");
    expect(screen.getAllByRole("option")).toHaveLength(1);
  });

  it("does not commit a value while the query only narrows the list", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <ComboSelect
        label="Judge model"
        items={items}
        value="openai/gpt-5"
        inputTestId="judge-model"
        onChange={onChange}
      />
    );

    await user.click(screen.getByTestId("judge-model"));
    await user.keyboard("anthropic");

    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(2));
    expect(onChange).not.toHaveBeenCalled();
  });
});
