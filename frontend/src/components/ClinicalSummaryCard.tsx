import type { ClinicalSummary } from "../api/types";

interface ClinicalSummaryCardProps {
  summary: ClinicalSummary;
}

const hasContent = (summary: ClinicalSummary): boolean =>
  Boolean(
    summary.diagnosis ||
      summary.requested_service ||
      summary.duration_of_symptoms ||
      summary.prior_treatments_tried.length ||
      summary.exam_findings.length ||
      summary.relevant_history.length,
  );

/** Renders the clinical summary extracted from a chart excerpt / referral.
 * Every field here is meant to reflect only what the referring clinician
 * actually wrote -- see the root README's Scope & Safety section and the
 * `extract_clinical_summary` prompt, which is constrained to never invent
 * or infer new clinical content. */
export function ClinicalSummaryCard({ summary }: ClinicalSummaryCardProps) {
  if (!hasContent(summary)) {
    return null;
  }

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 text-sm">
      <h4 className="text-xs font-semibold uppercase text-slate-500">Clinical summary</h4>

      {summary.diagnosis && (
        <div>
          <div className="text-xs font-medium text-slate-500">Diagnosis</div>
          <div>{summary.diagnosis}</div>
        </div>
      )}

      {summary.requested_service && (
        <div>
          <div className="text-xs font-medium text-slate-500">Requested service</div>
          <div>{summary.requested_service}</div>
        </div>
      )}

      {summary.duration_of_symptoms && (
        <div>
          <div className="text-xs font-medium text-slate-500">Duration of symptoms</div>
          <div>{summary.duration_of_symptoms}</div>
        </div>
      )}

      {summary.prior_treatments_tried.length > 0 && (
        <div>
          <div className="text-xs font-medium text-slate-500">Prior treatments tried</div>
          <ul className="list-inside list-disc space-y-0.5">
            {summary.prior_treatments_tried.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {summary.exam_findings.length > 0 && (
        <div>
          <div className="text-xs font-medium text-slate-500">Exam findings</div>
          <ul className="list-inside list-disc space-y-0.5">
            {summary.exam_findings.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {summary.relevant_history.length > 0 && (
        <div>
          <div className="text-xs font-medium text-slate-500">Relevant history</div>
          <ul className="list-inside list-disc space-y-0.5">
            {summary.relevant_history.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {summary.referring_provider_name && (
        <div>
          <div className="text-xs font-medium text-slate-500">Referring provider</div>
          <div>{summary.referring_provider_name}</div>
        </div>
      )}
    </div>
  );
}
