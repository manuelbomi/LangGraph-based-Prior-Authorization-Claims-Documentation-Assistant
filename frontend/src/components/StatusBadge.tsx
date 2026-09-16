import { STATUS_LABELS, type PARequestStatus } from "../api/types";

const STATUS_STYLES: Record<PARequestStatus, string> = {
  pending: "bg-slate-100 text-slate-600",
  running: "bg-sky-100 text-sky-700",
  awaiting_staff_review: "bg-amber-100 text-amber-700",
  ready_to_submit: "bg-teal-100 text-teal-700",
  submitted: "bg-indigo-100 text-indigo-700",
  approved: "bg-emerald-100 text-emerald-700",
  denied: "bg-rose-100 text-rose-700",
  more_info_requested: "bg-orange-100 text-orange-700",
  rejected: "bg-rose-100 text-rose-700",
  error: "bg-rose-100 text-rose-700",
};

interface StatusBadgeProps {
  status: PARequestStatus;
}

/** A small colored pill for a PA request's lifecycle status, used across
 * the tracking queue and detail views. See app/db/models.py::PARequest for
 * the full status lifecycle this mirrors. */
export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}>
      {STATUS_LABELS[status]}
    </span>
  );
}
