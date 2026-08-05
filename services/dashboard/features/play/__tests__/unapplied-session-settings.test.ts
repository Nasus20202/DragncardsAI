import { describe, expect, it } from "vitest";

import { unappliedSessionSettings } from "@/features/play/lib/session-draft";

const requested = {
  sessionPersona: "tryhard",
  allowedSubagents: ["kawaii-girl", "skibidi-toilet"],
};

describe("unappliedSessionSettings", () => {
  it("reports both settings when the response carries neither field", () => {
    // What an orchestrator predating the two settings answers: 200 OK, and a
    // session body with no `session_persona` and no `allowed_subagents` key.
    expect(unappliedSessionSettings(requested, {})).toBe(
      "The server did not apply the session persona or the allowed " +
        "subagents. The agent-orchestrator is most likely older than this " +
        "dashboard — rebuild and restart it so both are on the same version."
    );
  });

  it("reports nothing when the server stored what was asked for", () => {
    expect(
      unappliedSessionSettings(requested, {
        session_persona: "tryhard",
        allowed_subagents: ["kawaii-girl", "skibidi-toilet"],
      })
    ).toBeNull();
  });

  it("does not treat a reordered allowlist as a mismatch", () => {
    expect(
      unappliedSessionSettings(requested, {
        session_persona: "tryhard",
        allowed_subagents: ["skibidi-toilet", "kawaii-girl"],
      })
    ).toBeNull();
  });

  it("reports only the setting that did not stick", () => {
    expect(
      unappliedSessionSettings(requested, {
        session_persona: "tryhard",
        allowed_subagents: ["kawaii-girl"],
      })
    ).toContain("did not apply the allowed subagents.");
  });

  it("reports nothing when nothing was asked for and nothing came back", () => {
    // An absent field only matters when the request wanted something in it: a
    // save that asks for no persona and no allowlist has lost nothing, whatever
    // the server's age.
    expect(
      unappliedSessionSettings({ sessionPersona: "", allowedSubagents: [] }, {})
    ).toBeNull();
  });

  it("treats an explicit null persona as no persona", () => {
    expect(
      unappliedSessionSettings(
        { sessionPersona: "", allowedSubagents: [] },
        { session_persona: null, allowed_subagents: [] }
      )
    ).toBeNull();
  });

  it("reports a persona the server refused to clear", () => {
    expect(
      unappliedSessionSettings(
        { sessionPersona: "", allowedSubagents: ["kawaii-girl"] },
        { session_persona: "tryhard", allowed_subagents: ["kawaii-girl"] }
      )
    ).toContain("did not apply the session persona.");
  });
});
