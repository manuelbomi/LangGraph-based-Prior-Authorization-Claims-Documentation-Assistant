import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "../components/StatusBadge";

describe("StatusBadge", () => {
  it("renders the human-readable label for each status", () => {
    render(<StatusBadge status="ready_to_submit" />);
    expect(screen.getByText("Ready to submit")).toBeInTheDocument();
  });

  it("renders awaiting_staff_review with its label", () => {
    render(<StatusBadge status="awaiting_staff_review" />);
    expect(screen.getByText("Awaiting staff review")).toBeInTheDocument();
  });

  it("renders more_info_requested with its label", () => {
    render(<StatusBadge status="more_info_requested" />);
    expect(screen.getByText("More info requested")).toBeInTheDocument();
  });

  it("renders denied and rejected distinctly from approved", () => {
    const { rerender } = render(<StatusBadge status="approved" />);
    expect(screen.getByText("Approved").className).toContain("emerald");

    rerender(<StatusBadge status="denied" />);
    expect(screen.getByText("Denied").className).toContain("rose");

    rerender(<StatusBadge status="rejected" />);
    expect(screen.getByText("Rejected").className).toContain("rose");
  });
});
