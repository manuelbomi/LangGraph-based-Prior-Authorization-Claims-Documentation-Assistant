import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getPARequest, paRequestFileUrl, updatePARequestStatus } from "../api/client";
import { STATUS_LABELS, type TrackablePAStatus } from "../api/types";
import { ClinicalSummaryCard } from "../components/ClinicalSummaryCard";
import { CriteriaChecklistCard } from "../components/CriteriaChecklistCard";
import { DraftFormCard } from "../components/DraftFormCard";
import { StatusBadge } from "../components/StatusBadge";

const FINAL_STATUS_LABEL: Record<string, string> = {
  ready_to_submit: "Ready to submit",
  corrected_and_ready: "Ready to submit (edited)",
  rejected: "Rejected",
};

// Mirrors backend/app/api/routers/pa_requests.py::_ALLOWED_STATUS_TRANSITIONS.
// This is a plain field update modeling real-world tracking, not a graph
// re-entry -- see the root README's "Why LangGraph" section.
const ALLOWED_NEXT: Record<string, TrackablePAStatus[]> = {
  ready_to_submit: ["submitted"],
  submitted: ["approved", "denied", "more_info_requested"],
  more_info_requested: ["submitted"],
};

/** The PA request detail / "example analysis" view: chart excerpt link,
 * clinical summary, criteria checklist, draft form, trace log, and status
 * history, plus a control to advance the request's status -- the simple
 * mechanism this app uses to model tracking a request over days to weeks
 * without any additional LLM calls. */
export function PARequestDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [nextStatus, setNextStatus] = useState<TrackablePAStatus | "">("");
  const [note, setNote] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["pa-request", id],
    queryFn: () => getPARequest(id as string),
    enabled: Boolean(id),
  });

  const statusMutation = useMutation({
    mutationFn: () => updatePARequestStatus(id as string, { status: nextStatus as TrackablePAStatus, note }),
    onSuccess: () => {
      setNextStatus("");
      setNote("");
      queryClient.invalidateQueries({ queryKey: ["pa-request", id] });
      queryClient.invalidateQueries({ queryKey: ["pa-requests"] });
    },
  });

  if (isLoading) {
    return <p className="text-sm text-slate-400">Loading PA request...</p>;
  }
  if (error || !data) {
    return <p className="text-sm text-rose-600">Could not load this PA request.</p>;
  }

  const allowedNext = ALLOWED_NEXT[data.status] ?? [];

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <Link to="/tracking" className="text-xs text-brand-700 hover:underline">
          &larr; Back to PA request tracking
        </Link>
        <h2 className="mt-1 text-xl font-semibold text-slate-900">{data.original_filename}</h2>
        <p className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
          <StatusBadge status={data.status} />
          {data.final_status && <span>&middot; {FINAL_STATUS_LABEL[data.final_status] ?? data.final_status}</span>}
          <span>&middot; Payer: {data.payer_name}</span>
          <a
            href={paRequestFileUrl(data.id)}
            className="text-brand-700 hover:underline"
            target="_blank"
            rel="noreferrer"
          >
            view original chart excerpt
          </a>
        </p>
      </div>

      {data.error && <p className="rounded-md bg-rose-50 p-3 text-sm text-rose-700">{data.error}</p>}

      <ClinicalSummaryCard summary={data.clinical_summary} />
      <CriteriaChecklistCard checklist={data.criteria_checklist} />
      <DraftFormCard form={data.draft_form} />

      <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
        <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Update tracking status</h4>
        <p className="mb-3 text-xs text-slate-500">
          This models tracking a request through the payer's real-world review, which can take days to weeks.
          It is a plain status update, not a re-run of the drafting graph.
        </p>
        {allowedNext.length === 0 ? (
          <p className="text-xs text-slate-400">
            No further status update available from &quot;{STATUS_LABELS[data.status]}&quot;.
          </p>
        ) : (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (nextStatus) statusMutation.mutate();
            }}
          >
            <label className="block text-sm">
              <span className="mb-1 block text-xs text-slate-500">New status</span>
              <select
                value={nextStatus}
                onChange={(e) => setNextStatus(e.target.value as TrackablePAStatus)}
                aria-label="New status"
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              >
                <option value="">Choose a status...</option>
                {allowedNext.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABELS[s]}
                  </option>
                ))}
              </select>
            </label>
            <label className="block flex-1 text-sm" style={{ minWidth: "12rem" }}>
              <span className="mb-1 block text-xs text-slate-500">Note (optional)</span>
              <input
                value={note}
                onChange={(e) => setNote(e.target.value)}
                aria-label="Status update note"
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                placeholder="e.g. Submitted via payer portal"
              />
            </label>
            <button
              type="submit"
              disabled={!nextStatus || statusMutation.isPending}
              className="rounded-md bg-brand-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {statusMutation.isPending ? "Updating..." : "Update status"}
            </button>
          </form>
        )}
        {statusMutation.isError && (
          <p className="mt-2 text-sm text-rose-600">{(statusMutation.error as Error).message}</p>
        )}
      </div>

      {data.status_history.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Status history</h4>
          <ul className="space-y-1">
            {data.status_history.map((entry, i) => (
              <li key={i} className="text-xs text-slate-500">
                <span className="font-medium text-slate-700">{STATUS_LABELS[entry.status as keyof typeof STATUS_LABELS] ?? entry.status}</span>
                {" -- "}
                {new Date(entry.timestamp).toLocaleString()}
                {entry.note && <> &middot; {entry.note}</>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.trace.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <h4 className="mb-2 text-xs font-semibold uppercase text-slate-500">Trace</h4>
          <ul className="space-y-1 text-xs text-slate-500">
            {data.trace.map((event, i) => (
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
