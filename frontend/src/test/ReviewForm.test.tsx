import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { InterruptPayload } from "../api/types";
import { ReviewForm } from "../components/ReviewForm";

const INTERRUPT: InterruptPayload = {
  original_filename: "lumbar_mri_referral_jordan_blake.txt",
  clinical_summary: {
    diagnosis: "Chronic low back pain with left L5-S1 radiculopathy",
    requested_service: "Lumbar spine MRI without contrast",
    duration_of_symptoms: "Approximately 10 weeks",
    prior_treatments_tried: ["Physical therapy", "Naproxen"],
    exam_findings: ["Positive straight leg raise"],
    relevant_history: [],
    referring_provider_name: "Dr. Alicia Munoz, MD",
  },
  criteria_checklist: [
    {
      criterion_id: "meridian-health-plan-a",
      criterion_text: "Low back pain symptoms have been present for greater than 6 weeks.",
      status: "met",
      evidence: "Pain began approximately 10 weeks ago.",
    },
  ],
  draft_form: {
    patient_name: "Jordan Blake",
    patient_dob: "1979-03-14",
    patient_member_id: "MHP-5521309",
    payer_name: "Meridian Health Plan",
    provider_name: "Dr. Alicia Munoz, MD",
    provider_npi: "1447920033",
    requested_service: "Lumbar spine MRI without contrast",
    service_code: "72148",
    diagnosis: "Chronic low back pain with left L5-S1 radiculopathy",
    diagnosis_code: "M54.16",
    clinical_justification: "Draft justification referencing met criteria.",
  },
};

describe("ReviewForm", () => {
  it("pre-fills the draft form fields", () => {
    render(<ReviewForm interrupt={INTERRUPT} onDecision={vi.fn()} />);

    expect(screen.getByLabelText(/^requested service$/i)).toHaveValue("Lumbar spine MRI without contrast");
    expect(screen.getByLabelText(/procedure\/drug code/i)).toHaveValue("72148");
    expect(screen.getByLabelText(/^clinical justification$/i)).toHaveValue(
      "Draft justification referencing met criteria.",
    );
  });

  it("shows the draft-assistance-only safety banner", () => {
    render(<ReviewForm interrupt={INTERRUPT} onDecision={vi.fn()} />);
    expect(screen.getByText(/not a coverage decision/i)).toBeInTheDocument();
  });

  it("calls onDecision with approve and no corrected fields by default", async () => {
    const onDecision = vi.fn();
    const user = userEvent.setup();
    render(<ReviewForm interrupt={INTERRUPT} onDecision={onDecision} />);

    await user.click(screen.getByRole("button", { name: /^approve$/i }));

    expect(onDecision).toHaveBeenCalledWith({ decision: "approve", feedback: "" });
  });

  it("calls onDecision with reject and the reviewer note as feedback", async () => {
    const onDecision = vi.fn();
    const user = userEvent.setup();
    render(<ReviewForm interrupt={INTERRUPT} onDecision={onDecision} />);

    await user.type(screen.getByLabelText(/reviewer note/i), "Criteria not yet met, rejecting.");
    await user.click(screen.getByRole("button", { name: /^reject$/i }));

    expect(onDecision).toHaveBeenCalledWith(
      expect.objectContaining({ decision: "reject", feedback: "Criteria not yet met, rejecting." }),
    );
  });

  it("sends edited fields as corrected_draft_form when Edit & Approve is clicked", async () => {
    const onDecision = vi.fn();
    const user = userEvent.setup();
    render(<ReviewForm interrupt={INTERRUPT} onDecision={onDecision} />);

    const justification = screen.getByLabelText(/^clinical justification$/i);
    await user.clear(justification);
    await user.type(justification, "Edited justification with staff clarifications.");
    await user.click(screen.getByRole("button", { name: /edit & approve/i }));

    expect(onDecision).toHaveBeenCalledWith(
      expect.objectContaining({
        decision: "correct",
        corrected_draft_form: expect.objectContaining({
          clinical_justification: "Edited justification with staff clarifications.",
        }),
        corrected_criteria_checklist: expect.arrayContaining([
          expect.objectContaining({ criterion_id: "meridian-health-plan-a", status: "met" }),
        ]),
      }),
    );
  });

  it("allows changing a criterion's status and includes it in corrected_criteria_checklist", async () => {
    const onDecision = vi.fn();
    const user = userEvent.setup();
    render(<ReviewForm interrupt={INTERRUPT} onDecision={onDecision} />);

    await user.click(
      screen.getByLabelText(/low back pain symptoms have been present for greater than 6 weeks\. - unclear/i),
    );
    await user.click(screen.getByRole("button", { name: /edit & approve/i }));

    expect(onDecision).toHaveBeenCalledWith(
      expect.objectContaining({
        corrected_criteria_checklist: [expect.objectContaining({ status: "unclear" })],
      }),
    );
  });

  it("renders the criteria checklist", () => {
    render(<ReviewForm interrupt={INTERRUPT} onDecision={vi.fn()} />);
    expect(screen.getByText(/low back pain symptoms have been present/i)).toBeInTheDocument();
  });

  it("disables the buttons while submitting", () => {
    render(<ReviewForm interrupt={INTERRUPT} onDecision={vi.fn()} submitting />);

    expect(screen.getByRole("button", { name: /^approve$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /edit & approve/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^reject$/i })).toBeDisabled();
  });
});
