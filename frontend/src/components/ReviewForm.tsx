import { useState } from "react";

import type { CriterionAssessment, CriterionStatus, DraftForm, HumanDecisionRequest, InterruptPayload } from "../api/types";

interface ReviewFormProps {
  interrupt: InterruptPayload;
  onDecision: (decision: HumanDecisionRequest) => void;
  submitting?: boolean;
}

const STATUS_OPTIONS: CriterionStatus[] = ["met", "unmet", "unclear"];

/** The human-in-the-loop staff review panel -- the mandatory safety gate
 * this whole app is built around. This is administrative documentation
 * assistance only: it is NOT a coverage or medical-necessity decision, and
 * nothing drafted here is ready to submit to a payer until a licensed
 * staff member/clinician explicitly approves, edits, or rejects it. See
 * the root README's "Scope & Safety" section. */
export function ReviewForm({ interrupt, onDecision, submitting }: ReviewFormProps) {
  const form = interrupt.draft_form;
  const [requestedService, setRequestedService] = useState(form.requested_service);
  const [serviceCode, setServiceCode] = useState(form.service_code);
  const [diagnosis, setDiagnosis] = useState(form.diagnosis);
  const [diagnosisCode, setDiagnosisCode] = useState(form.diagnosis_code);
  const [clinicalJustification, setClinicalJustification] = useState(form.clinical_justification);
  const [checklist, setChecklist] = useState<CriterionAssessment[]>(interrupt.criteria_checklist);
  const [feedback, setFeedback] = useState("");

  const updateCriterion = (index: number, field: keyof CriterionAssessment, value: string) => {
    setChecklist((prev) => prev.map((item, i) => (i === index ? { ...item, [field]: value } : item)));
  };

  const buildCorrectedForm = (): DraftForm => ({
    ...form,
    requested_service: requestedService,
    service_code: serviceCode,
    diagnosis,
    diagnosis_code: diagnosisCode,
    clinical_justification: clinicalJustification,
  });

  const submit = (decision: HumanDecisionRequest["decision"]) => {
    const payload: HumanDecisionRequest = { decision, feedback };
    if (decision === "correct") {
      payload.corrected_draft_form = buildCorrectedForm();
      payload.corrected_criteria_checklist = checklist;
    }
    onDecision(payload);
  };

  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-5">
      <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-amber-700">Staff review required</h3>
      <p className="mb-4 text-sm text-amber-900">
        <strong>Draft assistance only -- not a coverage decision.</strong> This assistant drafts
        prior-authorization paperwork from the chart excerpt above; it does not decide coverage or medical
        necessity (that is the payer's decision) and does not provide medical advice. Review and correct the
        fields below as needed, then Approve, Edit &amp; Approve, or Reject. Nothing is queued as ready to submit
        until you decide.
      </p>

      <div className="mb-4 grid gap-4 md:grid-cols-2">
        <div className="space-y-3 rounded-lg border border-amber-200 bg-white p-4">
          <h4 className="text-xs font-semibold uppercase text-slate-500">Draft PA form (editable)</h4>

          <div className="grid grid-cols-2 gap-2 text-xs text-slate-500">
            <div>
              <span className="block">Patient</span>
              <span className="text-slate-700">{form.patient_name}</span>
            </div>
            <div>
              <span className="block">Payer</span>
              <span className="text-slate-700">{form.payer_name}</span>
            </div>
          </div>

          <label className="block text-sm">
            <span className="text-xs text-slate-500">Requested service</span>
            <input
              className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1"
              value={requestedService}
              onChange={(e) => setRequestedService(e.target.value)}
              aria-label="Requested service"
            />
          </label>

          <label className="block text-sm">
            <span className="text-xs text-slate-500">Procedure/drug code</span>
            <input
              className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1 font-mono"
              value={serviceCode}
              onChange={(e) => setServiceCode(e.target.value)}
              aria-label="Procedure or drug code"
            />
          </label>

          <label className="block text-sm">
            <span className="text-xs text-slate-500">Diagnosis</span>
            <input
              className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1"
              value={diagnosis}
              onChange={(e) => setDiagnosis(e.target.value)}
              aria-label="Diagnosis"
            />
          </label>

          <label className="block text-sm">
            <span className="text-xs text-slate-500">Diagnosis code</span>
            <input
              className="mt-0.5 w-full rounded border border-slate-300 px-2 py-1 font-mono"
              value={diagnosisCode}
              onChange={(e) => setDiagnosisCode(e.target.value)}
              aria-label="Diagnosis code"
            />
          </label>

          <label className="block text-sm">
            <span className="text-xs text-slate-500">Clinical justification</span>
            <textarea
              className="mt-0.5 w-full rounded border border-slate-300 p-2"
              rows={6}
              value={clinicalJustification}
              onChange={(e) => setClinicalJustification(e.target.value)}
              aria-label="Clinical justification"
            />
          </label>
        </div>

        <div className="space-y-3">
          {checklist.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-white p-4 text-sm">
              <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">
                Criteria checklist (editable, draft assessment only)
              </h4>
              <div className="space-y-3">
                {checklist.map((item, i) => (
                  <fieldset key={item.criterion_id || i} className="border-t border-slate-100 pt-2 first:border-t-0 first:pt-0">
                    <legend className="mb-1 text-xs font-medium text-slate-600">{item.criterion_text}</legend>
                    <div className="mb-1 flex gap-2">
                      {STATUS_OPTIONS.map((status) => (
                        <label key={status} className="flex items-center gap-1 text-xs text-slate-600">
                          <input
                            type="radio"
                            name={`criterion-status-${item.criterion_id || i}`}
                            checked={item.status === status}
                            onChange={() => updateCriterion(i, "status", status)}
                            aria-label={`${item.criterion_text} - ${status}`}
                          />
                          {status}
                        </label>
                      ))}
                    </div>
                    <input
                      className="w-full rounded border border-slate-300 px-2 py-1 text-xs"
                      value={item.evidence}
                      onChange={(e) => updateCriterion(i, "evidence", e.target.value)}
                      aria-label={`${item.criterion_text} evidence`}
                      placeholder="Evidence"
                    />
                  </fieldset>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <textarea
        className="mb-3 w-full rounded-md border border-slate-300 p-2 text-sm"
        rows={2}
        placeholder="Reviewer note (optional) -- why you approved, edited, or rejected this draft"
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        aria-label="Reviewer note"
      />

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={submitting}
          onClick={() => submit("approve")}
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={() => submit("correct")}
          className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          Edit &amp; Approve
        </button>
        <button
          type="button"
          disabled={submitting}
          onClick={() => submit("reject")}
          className="rounded-md bg-rose-600 px-4 py-2 text-sm font-medium text-white hover:bg-rose-700 disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
