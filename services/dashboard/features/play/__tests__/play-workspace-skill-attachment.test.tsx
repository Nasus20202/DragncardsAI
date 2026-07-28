import { beforeEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";

import {
  getApi,
  renderPlayWorkspace,
  resetPlayWorkspaceEnvironment,
  sessionDetail,
} from "@/features/play/__tests__/play-workspace-test-support";

const api = getApi();

const withSkillA = {
  ...sessionDetail,
  skills: [
    {
      id: "session-1:skill-a",
      skill_name: "skill-a",
      skill_path: "/skills/a",
      created_at: "2026-05-11T00:00:00Z",
    },
  ],
};

async function waitForLoadedSession() {
  await waitFor(() =>
    expect(screen.getByTestId("selected-session-name")).toHaveTextContent(
      "Existing session"
    )
  );
}

describe("PlayWorkspace skill attachment from the composer", () => {
  beforeEach(() => {
    resetPlayWorkspaceEnvironment();
  });

  it("shows the session's attached skills on the composer", async () => {
    api.getSession.mockResolvedValue(withSkillA);

    renderPlayWorkspace();
    await waitForLoadedSession();

    await waitFor(() =>
      expect(screen.getByTestId("prompt-attached-skills")).toHaveTextContent(
        "skill-a"
      )
    );
  });

  it("attaches a mentioned skill immediately and shows it in the settings panel", async () => {
    renderPlayWorkspace();
    await waitForLoadedSession();

    fireEvent.click(screen.getByRole("button", { name: /attach skill-b/i }));

    await waitFor(() =>
      expect(api.addSkill).toHaveBeenCalledWith("session-1", "skill-b")
    );
    await waitFor(() =>
      expect(screen.getByTestId("draft-skills")).toHaveTextContent("skill-b")
    );
    expect(screen.getByTestId("prompt-attached-skills")).toHaveTextContent(
      "skill-b"
    );
  });

  it("shows a chip for a skill enabled in the settings panel", async () => {
    renderPlayWorkspace();
    await waitForLoadedSession();

    fireEvent.click(
      screen.getByRole("button", { name: /enable skill-b in settings/i })
    );

    await waitFor(() =>
      expect(screen.getByTestId("prompt-attached-skills")).toHaveTextContent(
        "skill-b"
      )
    );
    // The settings panel still defers persistence to Save.
    expect(api.addSkill).not.toHaveBeenCalled();
  });

  it("detaches a skill from a composer chip immediately", async () => {
    api.getSession.mockResolvedValue(withSkillA);

    renderPlayWorkspace();
    await waitForLoadedSession();
    await waitFor(() =>
      expect(screen.getByTestId("draft-skills")).toHaveTextContent("skill-a")
    );

    fireEvent.click(screen.getByRole("button", { name: /detach skill-a/i }));

    await waitFor(() =>
      expect(api.removeSkill).toHaveBeenCalledWith("session-1", "skill-a")
    );
    await waitFor(() =>
      expect(screen.getByTestId("draft-skills")).toHaveTextContent("")
    );
    expect(screen.getByTestId("prompt-attached-skills")).toHaveTextContent("");
  });

  it("keeps unsaved settings-panel skill edits when attaching from the composer", async () => {
    renderPlayWorkspace();
    await waitForLoadedSession();

    fireEvent.click(
      screen.getByRole("button", { name: /enable skill-b in settings/i })
    );
    await waitFor(() =>
      expect(screen.getByTestId("draft-skills")).toHaveTextContent("skill-b")
    );

    fireEvent.click(screen.getByRole("button", { name: /attach skill-a/i }));

    await waitFor(() =>
      expect(api.addSkill).toHaveBeenCalledWith("session-1", "skill-a")
    );
    await waitFor(() =>
      expect(screen.getByTestId("draft-skills")).toHaveTextContent(
        "skill-b,skill-a"
      )
    );
  });

  it("names a mentioned skill when the prompt is submitted", async () => {
    api.getSession.mockResolvedValue(withSkillA);

    renderPlayWorkspace();
    await waitForLoadedSession();
    await waitFor(() =>
      expect(screen.getByTestId("prompt-attached-skills")).toHaveTextContent(
        "skill-a"
      )
    );

    fireEvent.change(screen.getByLabelText("Prompt input"), {
      target: { value: "@skill-a play the villain phase" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit prompt/i }));

    await waitFor(() =>
      expect(api.submitPrompt).toHaveBeenCalledWith(
        "session-1",
        "@skill-a play the villain phase",
        ["skill-a"]
      )
    );
  });

  it("names nothing for an @ token that is not an attached skill", async () => {
    api.getSession.mockResolvedValue(withSkillA);

    renderPlayWorkspace();
    await waitForLoadedSession();

    fireEvent.change(screen.getByLabelText("Prompt input"), {
      target: { value: "mail me at me@example.com about @skill-b" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit prompt/i }));

    await waitFor(() =>
      expect(api.submitPrompt).toHaveBeenCalledWith(
        "session-1",
        "mail me at me@example.com about @skill-b",
        []
      )
    );
  });

  it("surfaces a rejected attachment and leaves the skill unattached", async () => {
    api.addSkill.mockRejectedValueOnce(new Error("Unknown skill"));

    renderPlayWorkspace();
    await waitForLoadedSession();

    fireEvent.click(screen.getByRole("button", { name: /attach skill-b/i }));

    await waitFor(() =>
      expect(screen.getByTestId("error-text")).toHaveTextContent(
        "Unknown skill"
      )
    );
    expect(screen.getByTestId("draft-skills")).toHaveTextContent("");
    expect(screen.getByTestId("prompt-attached-skills")).toHaveTextContent("");
  });
});
