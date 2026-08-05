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
}: {
  initial: JudgeDraft;
  onDraft?: (next: JudgeDraft) => void;
}) {
  const [draftState, setDraftState] = useState<JudgeDraft>(initial);
  return (
    <JudgeConfigPanel
      draft={draftState}
      providers={PROVIDERS}
      skills={SKILLS}
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

describe("reference selection cap", () => {
  it("stops at the server's limit and keeps selected rows togglable", async () => {
    const many: SkillDefinitionResponse[] = [
      {
        name: "rules",
        path: "/s/rules",
        description: "",
        metadata: {},
        references: Array.from({ length: 12 }, (_, i) => `r${i}.md`),
      },
    ];
    const selected = Array.from({ length: 8 }, (_, i) => `rules/r${i}.md`);

    render(
      <JudgeConfigPanel
        draft={draft({
          selectedSkills: ["rules"],
          selectedSkillReferences: selected,
        })}
        providers={PROVIDERS}
        skills={many}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByText("8/8")).toBeInTheDocument();
    // An unselected row past the limit is disabled...
    expect(
      within(screen.getByTestId("judge-skill-reference-rules/r8.md")).getByRole(
        "switch"
      )
    ).toBeDisabled();
    // ...while an already-selected one stays live, so a choice can be swapped.
    expect(
      within(screen.getByTestId("judge-skill-reference-rules/r0.md")).getByRole(
        "switch"
      )
    ).not.toBeDisabled();
  });
});
