import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

import { RestoreControl } from "@/features/history/components/restore-control";

describe("RestoreControl", () => {
  it("defaults to the new branchable session mode", () => {
    render(<RestoreControl targetSeq={4} onRestore={vi.fn()} />);

    const newRadio = screen.getByRole("radio", {
      name: /new branchable session/i,
    });
    const inPlaceRadio = screen.getByRole("radio", {
      name: /in-place overwrite/i,
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

    fireEvent.click(screen.getByRole("radio", { name: /in-place overwrite/i }));
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
