import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import { RestoreControl } from "@/features/history/components/restore-control";

describe("RestoreControl", () => {
  it("defaults to the safe into-a-new-game mode", () => {
    render(<RestoreControl targetSeq={4} onRestore={vi.fn()} />);

    const newRadio = screen.getByRole("radio", {
      name: /into a new game/i,
    });
    const inPlaceRadio = screen.getByRole("radio", {
      name: /over this game/i,
    });
    expect(newRadio).toBeChecked();
    expect(inPlaceRadio).not.toBeChecked();
    expect(
      screen.queryByTestId("restore-in-place-warning")
    ).not.toBeInTheDocument();
  });

  it("restores with the selected target seq and new mode in one click", async () => {
    const onRestore = vi.fn().mockResolvedValue({ status: "completed" });
    render(<RestoreControl targetSeq={7} onRestore={onRestore} />);

    fireEvent.click(screen.getByTestId("restore-submit"));

    await waitFor(() => {
      expect(onRestore).toHaveBeenCalledWith(7, "new");
    });
    expect(await screen.findByTestId("restore-success")).toBeInTheDocument();
  });

  it("warns and requires confirmation before an in-place overwrite", async () => {
    const onRestore = vi.fn().mockResolvedValue({ status: "completed" });
    render(<RestoreControl targetSeq={3} onRestore={onRestore} />);

    fireEvent.click(screen.getByRole("radio", { name: /over this game/i }));
    expect(screen.getByTestId("restore-in-place-warning")).toBeInTheDocument();

    // First click only confirms — no request yet.
    fireEvent.click(screen.getByTestId("restore-submit"));
    expect(onRestore).not.toHaveBeenCalled();

    // Second click sends the in_place restore.
    fireEvent.click(screen.getByTestId("restore-submit"));
    await waitFor(() => {
      expect(onRestore).toHaveBeenCalledWith(3, "in_place");
    });
  });

  it("surfaces an unverified/divergent restore as a warning, not success", async () => {
    const onRestore = vi.fn().mockResolvedValue({
      status: "completed",
      status_verified: false,
      divergence: "live state hash differs from snapshot",
    });
    render(<RestoreControl targetSeq={5} onRestore={onRestore} />);

    fireEvent.click(screen.getByTestId("restore-submit"));

    expect(await screen.findByTestId("restore-warning")).toHaveTextContent(
      "live state hash differs from snapshot"
    );
    expect(screen.queryByTestId("restore-success")).not.toBeInTheDocument();
  });

  it("treats a verified outcome (no status_verified flag) as success", async () => {
    const onRestore = vi.fn().mockResolvedValue({ status: "completed" });
    render(<RestoreControl targetSeq={6} onRestore={onRestore} />);

    fireEvent.click(screen.getByTestId("restore-submit"));

    expect(await screen.findByTestId("restore-success")).toBeInTheDocument();
    expect(screen.queryByTestId("restore-warning")).not.toBeInTheDocument();
  });

  it("surfaces a failure outcome without claiming success", async () => {
    const onRestore = vi
      .fn()
      .mockResolvedValue({ status: "failed", detail: "snapshot missing" });
    render(<RestoreControl targetSeq={9} onRestore={onRestore} />);

    fireEvent.click(screen.getByTestId("restore-submit"));

    expect(await screen.findByTestId("restore-failure")).toHaveTextContent(
      "snapshot missing"
    );
    expect(screen.queryByTestId("restore-success")).not.toBeInTheDocument();
  });

  it("surfaces a thrown error as a failure", async () => {
    const onRestore = vi.fn().mockRejectedValue(new Error("network down"));
    render(<RestoreControl targetSeq={2} onRestore={onRestore} />);

    fireEvent.click(screen.getByTestId("restore-submit"));

    expect(await screen.findByTestId("restore-failure")).toHaveTextContent(
      "network down"
    );
  });

  it("disables the control when no moment is selected", () => {
    render(<RestoreControl targetSeq={null} onRestore={vi.fn()} />);
    expect(screen.getByTestId("restore-submit")).toBeDisabled();
  });
});

describe("RestoreControl clarity (DRA-28)", () => {
  it("marks the two modes as safe and destructive before either is clicked", () => {
    render(<RestoreControl targetSeq={4} onRestore={vi.fn()} />);

    // The choice is between changing a game and not changing it, so which is
    // which has to be readable without clicking either one.
    const safe = screen.getByRole("radio", { name: /into a new game/i });
    const destructive = screen.getByRole("radio", { name: /over this game/i });
    expect(safe).toHaveAccessibleName(/safe/i);
    expect(safe).toHaveAccessibleName(/not changed/i);
    expect(destructive).toHaveAccessibleName(/destructive/i);
  });

  it("names the action on the button rather than saying only 'Restore'", () => {
    render(<RestoreControl targetSeq={4} onRestore={vi.fn()} />);

    expect(screen.getByTestId("restore-submit")).toHaveTextContent(
      /create the new game/i
    );
    fireEvent.click(screen.getByRole("radio", { name: /over this game/i }));
    expect(screen.getByTestId("restore-submit")).toHaveTextContent(
      /rewind this game/i
    );
  });

  it("names the new room and links to it after a branch restore", async () => {
    const onRestore = vi.fn().mockResolvedValue({
      status: "restored",
      mode: "new",
      session_id: "sess-1",
      room_slug: "starry-liquid-8190",
    });
    render(
      <RestoreControl
        targetSeq={7}
        onRestore={onRestore}
        frontendUrl="http://localhost:3000"
      />
    );

    fireEvent.click(screen.getByTestId("restore-submit"));

    const success = await screen.findByTestId("restore-success");
    expect(success).toHaveTextContent(/starry-liquid-8190/);
    // A branch restore whose product cannot be reached is indistinguishable
    // from one that never happened, which is what DRA-26 reported.
    expect(screen.getByTestId("restore-open-new-game")).toHaveAttribute(
      "href",
      "http://localhost:3000/room/starry-liquid-8190"
    );
  });

  it("says the live game was rewound after an in-place restore", async () => {
    const onRestore = vi
      .fn()
      .mockResolvedValue({ status: "restored", mode: "in_place" });
    render(<RestoreControl targetSeq={3} onRestore={onRestore} />);

    fireEvent.click(screen.getByRole("radio", { name: /over this game/i }));
    fireEvent.click(screen.getByTestId("restore-submit"));
    fireEvent.click(screen.getByTestId("restore-submit"));

    const success = await screen.findByTestId("restore-success");
    expect(success).toHaveTextContent(/rewound to the selected moment/i);
    expect(
      screen.queryByTestId("restore-open-new-game")
    ).not.toBeInTheDocument();
  });

  it("reports an unrestored agent conversation as a note, not a failure", async () => {
    const onRestore = vi.fn().mockResolvedValue({
      status: "restored",
      mode: "in_place",
      agent_context_restored: false,
      agent_context_note:
        "The game state was restored, but no active agent session is bound to this game.",
    });
    render(<RestoreControl targetSeq={3} onRestore={onRestore} />);

    fireEvent.click(screen.getByRole("radio", { name: /over this game/i }));
    fireEvent.click(screen.getByTestId("restore-submit"));
    fireEvent.click(screen.getByTestId("restore-submit"));

    // This is the DRA-26 404: the rewind DID happen, so it must not read as a
    // failed restore.
    expect(await screen.findByTestId("restore-success")).toBeInTheDocument();
    expect(screen.getByTestId("restore-agent-note")).toHaveTextContent(
      /no active agent session/i
    );
    expect(screen.queryByTestId("restore-failure")).not.toBeInTheDocument();
  });
});
