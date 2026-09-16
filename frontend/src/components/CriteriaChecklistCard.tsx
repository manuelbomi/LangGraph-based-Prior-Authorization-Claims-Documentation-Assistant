import type { CriterionAssessment, CriterionStatus } from "../api/types";

interface CriteriaChecklistCardProps {
  checklist: CriterionAssessment[];
}

const STATUS_STYLES: Record<CriterionStatus, string> = {
  met: "bg-emerald-100 text-emerald-700",
  unmet: "bg-rose-100 text-rose-700",
  unclear: "bg-amber-100 text-amber-700",
};

const STATUS_LABELS: Record<CriterionStatus, string> = {
  met: "Met",
  unmet: "Unmet",
  unclear: "Unclear",
};

/** Renders the payer medical-necessity criteria checklist with evidence
 * citations back to the chart. ALWAYS labeled a draft assessment for staff
 * review -- this is never a coverage or medical-necessity determination,
 * which is the payer's decision alone. See the root README's Scope &
 * Safety section and `match_policy_criteria_node`. */
export function CriteriaChecklistCard({ checklist }: CriteriaChecklistCardProps) {
  if (checklist.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 text-sm">
      <h4 className="text-xs font-semibold uppercase text-slate-500">
        Payer medical-necessity criteria{" "}
        <span className="normal-case text-slate-400">(draft assessment for staff review, not a coverage decision)</span>
      </h4>
      <ul className="space-y-2">
        {checklist.map((item, i) => (
          <li key={item.criterion_id || i} className="border-t border-slate-100 pt-2 first:border-t-0 first:pt-0">
            <div className="mb-1 flex items-center gap-2">
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[item.status]}`}>
                {STATUS_LABELS[item.status]}
              </span>
              <span className="font-medium text-slate-700">{item.criterion_text}</span>
            </div>
            <p className="text-xs text-slate-500">Evidence: {item.evidence}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
