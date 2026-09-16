import type { ClinicalSummary, CriterionAssessment, DraftForm, TraceEventOut } from "../api/types";
import { ClinicalSummaryCard } from "./ClinicalSummaryCard";
import { CriteriaChecklistCard } from "./CriteriaChecklistCard";
import { DraftFormCard } from "./DraftFormCard";

interface NodePanelProps {
  clinicalSummary: ClinicalSummary;
  criteriaChecklist: CriterionAssessment[];
  draftForm: DraftForm;
  trace: TraceEventOut[];
}

/** Live output panel for the New PA Request page: shows the clinical
 * summary, criteria checklist, and drafted form as they arrive over the
 * SSE stream, plus the raw node trace log. */
export function NodePanel({ clinicalSummary, criteriaChecklist, draftForm, trace }: NodePanelProps) {
  return (
    <div className="space-y-4">
      <ClinicalSummaryCard summary={clinicalSummary} />
      <CriteriaChecklistCard checklist={criteriaChecklist} />
      <DraftFormCard form={draftForm} />

      {trace.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Trace</h4>
          <ul className="space-y-1 text-xs text-slate-500">
            {trace.map((event, i) => (
              <li key={i}>
                <span className="font-mono text-slate-400">{event.node}</span> -- {event.summary}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
