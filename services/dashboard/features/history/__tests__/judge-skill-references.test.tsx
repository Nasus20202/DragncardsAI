import "@testing-library/jest-dom";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { JudgeConfigPanel } from "@/features/history/components/judge-config";
import { installResizeObserver } from "@/features/shared/__tests__/heroui-test-env";
import {
  JudgeDraft,
  assembleJudgeConfig,
} from "@/features/history/lib/judge-config";
import {
  ProviderResponse,
  SkillDefinitionResponse,
} from "@/features/shared/lib/types";

const PROVIDERS: ProviderResponse[] = [
  {
    provider_id: "openrouter",
    model_prefix: "openrouter",
    models: ["openai/gpt-5"],
    available: true,
    error: null,
  },
];

const RULES_ERRATA = "rules/resources/errata.md";
const RULES_TIMING = "rules/resources/timing.md";

const SKILLS: SkillDefinitionResponse[] = [
  {
    name: "rules",
    path: "/s/rules",
    description: "The Marvel Champions rules reference.",
    metadata: {},
    references: ["resources/errata.md", "resources/timing.md"],
  },
  {
    name: "bare",
    path: "/s/bare",
    description: "",
    metadata: {},
    references: [],
  },
];

function draft(overrides: Partial<JudgeDraft> = {}): JudgeDraft {
  return {
    providerId: "openrouter",
    modelName: "openai/gpt-5",
    reasoningEnabled: false,
    reasoningEffort: "medium",
    reasoningMaxTokens: "",
    promptOverride: "",
    selectedSkills: [],
    selectedSkillReferences: [],
    ...overrides,
  };
}

/** Render the panel against a controlled draft, the way the workspace does. */
function PanelHarness({
  initial,
  onDraft,
  skills = SKILLS,
}: {
  initial: JudgeDraft;
  onDraft?: (next: JudgeDraft) => void;
  skills?: SkillDefinitionResponse[];
}) {
  const [draftState, setDraftState] = useState<JudgeDraft>(initial);
  return (
    <JudgeConfigPanel
      draft={draftState}
      providers={PROVIDERS}
      skills={skills}
      onChange={(next) => {
        setDraftState(next);
        onDraft?.(next);
      }}
    />
  );
}

/** Flip the switch inside the toggle row carrying the given test id. */
async function flipSwitch(
  user: ReturnType<typeof userEvent.setup>,
  testId: string
) {
  await user.click(within(screen.getByTestId(testId)).getByRole("switch"));
}

beforeAll(installResizeObserver);

describe("judge skill references", () => {
  it("shows no reference section until a skill with references is selected", () => {
    render(
      <JudgeConfigPanel
        draft={draft()}
        providers={PROVIDERS}
        skills={SKILLS}
        onChange={vi.fn()}
      />
    );

    expect(screen.queryByTestId("judge-skill-references")).toBeNull();
  });

  it("renders a toggle per reference of a selected skill", () => {
    render(
      <JudgeConfigPanel
        draft={draft({ selectedSkills: ["rules"] })}
        providers={PROVIDERS}
        skills={SKILLS}
        onChange={vi.fn()}
      />
    );

    const section = screen.getByTestId("judge-skill-references");
    expect(
      within(section).getByTestId(`judge-skill-reference-${RULES_ERRATA}`)
    ).toBeInTheDocument();
    expect(
      within(section).getByTestId(`judge-skill-reference-${RULES_TIMING}`)
    ).toBeInTheDocument();
  });

  it("renders nothing for a selected skill that ships no references", () => {
    render(
      <JudgeConfigPanel
        draft={draft({ selectedSkills: ["bare"] })}
        providers={PROVIDERS}
        skills={SKILLS}
        onChange={vi.fn()}
      />
    );

    expect(screen.queryByTestId("judge-skill-references")).toBeNull();
  });

  it("reveals reference toggles once the skill itself is switched on", async () => {
    const user = userEvent.setup();
    render(<PanelHarness initial={draft()} />);

    expect(screen.queryByTestId("judge-skill-references")).toBeNull();

    await flipSwitch(user, "judge-skill-rules");

    expect(
      screen.getByTestId(`judge-skill-reference-${RULES_ERRATA}`)
    ).toBeInTheDocument();
  });

  it("puts the toggled reference into the assembled judge config", async () => {
    const user = userEvent.setup();
    const drafts: JudgeDraft[] = [];
    render(
      <PanelHarness
        initial={draft({ selectedSkills: ["rules"] })}
        onDraft={(next) => drafts.push(next)}
      />
    );

    await flipSwitch(user, `judge-skill-reference-${RULES_ERRATA}`);

    const assembled = assembleJudgeConfig(drafts[drafts.length - 1]);
    expect(assembled?.skill_references).toEqual([RULES_ERRATA]);
  });

  it("drops a skill's references when the skill is deselected", async () => {
    const user = userEvent.setup();
    const drafts: JudgeDraft[] = [];
    render(
      <PanelHarness
        initial={draft({
          selectedSkills: ["rules"],
          selectedSkillReferences: [RULES_ERRATA],
        })}
        onDraft={(next) => drafts.push(next)}
      />
    );

    await flipSwitch(user, "judge-skill-rules");

    const latest = drafts[drafts.length - 1];
    expect(latest.selectedSkillReferences).toEqual([]);
    expect(screen.queryByTestId("judge-skill-references")).toBeNull();
    expect(assembleJudgeConfig(latest)).not.toHaveProperty("skill_references");
  });
});

/** One skill shipping twelve reference files -- more than the old cap of 8. */
const MANY: SkillDefinitionResponse[] = [
  {
    name: "rules",
    path: "/s/rules",
    description: "",
    metadata: {},
    references: Array.from({ length: 12 }, (_, i) => `r${i}.md`),
  },
];

/** Two skills with references, for asserting that group actions stay scoped. */
const TWO_GROUPS: SkillDefinitionResponse[] = [
  {
    name: "rules",
    path: "/s/rules",
    description: "",
    metadata: {},
    references: ["a.md", "b.md"],
  },
  {
    name: "tactics",
    path: "/s/tactics",
    description: "",
    metadata: {},
    references: ["x.md", "y.md"],
  },
];

describe("reference selection has no count limit", () => {
  it("lets a ninth reference be selected and disables no row by count", async () => {
    const user = userEvent.setup();
    const drafts: JudgeDraft[] = [];
    const selected = Array.from({ length: 8 }, (_, i) => `rules/r${i}.md`);

    render(
      <PanelHarness
        initial={draft({
          selectedSkills: ["rules"],
          selectedSkillReferences: selected,
        })}
        onDraft={(next) => drafts.push(next)}
        skills={MANY}
      />
    );

    // The counter reports the catalogue size, not a cap.
    expect(screen.getByText("8/12")).toBeInTheDocument();

    // No row is disabled while eight are already picked.
    for (let i = 0; i < 12; i += 1) {
      expect(
        within(
          screen.getByTestId(`judge-skill-reference-rules/r${i}.md`)
        ).getByRole("switch")
      ).not.toBeDisabled();
    }

    await flipSwitch(user, "judge-skill-reference-rules/r8.md");

    const latest = drafts[drafts.length - 1];
    expect(latest.selectedSkillReferences).toHaveLength(9);
    expect(latest.selectedSkillReferences).toContain("rules/r8.md");
    expect(assembleJudgeConfig(latest)?.skill_references).toHaveLength(9);
    expect(screen.getByText("9/12")).toBeInTheDocument();
  });

  it("selects every reference of every selected skill from the header", async () => {
    const user = userEvent.setup();
    const drafts: JudgeDraft[] = [];
    render(
      <PanelHarness
        initial={draft({ selectedSkills: ["rules", "tactics"] })}
        onDraft={(next) => drafts.push(next)}
        skills={TWO_GROUPS}
      />
    );

    await user.click(screen.getByTestId("judge-skill-references-select-all"));

    expect(drafts[drafts.length - 1].selectedSkillReferences).toEqual([
      "rules/a.md",
      "rules/b.md",
      "tactics/x.md",
      "tactics/y.md",
    ]);
    expect(screen.getByText("4/4")).toBeInTheDocument();
    // Nothing left to select, so the control retires itself.
    expect(
      screen.getByTestId("judge-skill-references-select-all")
    ).toBeDisabled();
  });

  it("empties the selection from the header's clear all", async () => {
    const user = userEvent.setup();
    const drafts: JudgeDraft[] = [];
    render(
      <PanelHarness
        initial={draft({
          selectedSkills: ["rules", "tactics"],
          selectedSkillReferences: ["rules/a.md", "tactics/y.md"],
        })}
        onDraft={(next) => drafts.push(next)}
        skills={TWO_GROUPS}
      />
    );

    await user.click(screen.getByTestId("judge-skill-references-clear-all"));

    expect(drafts[drafts.length - 1].selectedSkillReferences).toEqual([]);
    expect(screen.getByText("0/4")).toBeInTheDocument();
    expect(
      screen.getByTestId("judge-skill-references-clear-all")
    ).toBeDisabled();
  });

  it("keeps a group's All and None scoped to that group", async () => {
    const user = userEvent.setup();
    const drafts: JudgeDraft[] = [];
    render(
      <PanelHarness
        initial={draft({
          selectedSkills: ["rules", "tactics"],
          selectedSkillReferences: ["tactics/y.md"],
        })}
        onDraft={(next) => drafts.push(next)}
        skills={TWO_GROUPS}
      />
    );

    await user.click(
      screen.getByTestId("judge-skill-references-group-all-rules")
    );

    // The other group's selection survives untouched.
    expect(drafts[drafts.length - 1].selectedSkillReferences).toEqual([
      "tactics/y.md",
      "rules/a.md",
      "rules/b.md",
    ]);

    await user.click(
      screen.getByTestId("judge-skill-references-group-none-rules")
    );

    expect(drafts[drafts.length - 1].selectedSkillReferences).toEqual([
      "tactics/y.md",
    ]);
  });

  it("adds only the missing entries when selecting all over a partial selection", async () => {
    const user = userEvent.setup();
    const drafts: JudgeDraft[] = [];
    render(
      <PanelHarness
        initial={draft({
          selectedSkills: ["rules", "tactics"],
          selectedSkillReferences: ["tactics/x.md", "rules/b.md"],
        })}
        onDraft={(next) => drafts.push(next)}
        skills={TWO_GROUPS}
      />
    );

    await user.click(screen.getByTestId("judge-skill-references-select-all"));

    const next = drafts[drafts.length - 1].selectedSkillReferences;
    // No duplicates, and the pre-existing entries keep their order at the front.
    expect(next).toEqual([
      "tactics/x.md",
      "rules/b.md",
      "rules/a.md",
      "tactics/y.md",
    ]);
    expect(new Set(next).size).toBe(next.length);
  });

  it("disables every bulk control while an evaluation is in flight", () => {
    render(
      <JudgeConfigPanel
        draft={draft({
          selectedSkills: ["rules", "tactics"],
          selectedSkillReferences: ["rules/a.md"],
        })}
        providers={PROVIDERS}
        skills={TWO_GROUPS}
        disabled
        onChange={vi.fn()}
      />
    );

    for (const testId of [
      "judge-skill-references-select-all",
      "judge-skill-references-clear-all",
      "judge-skill-references-group-all-rules",
      "judge-skill-references-group-none-rules",
    ]) {
      expect(screen.getByTestId(testId)).toBeDisabled();
    }
    expect(
      within(screen.getByTestId("judge-skill-reference-rules/a.md")).getByRole(
        "switch"
      )
    ).toBeDisabled();
  });
});
