import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { listPARequests, listPatients } from "../api/client";
import { STATUS_LABELS, type PARequestStatus } from "../api/types";
import { StatusBadge } from "../components/StatusBadge";

const ALL_STATUSES = Object.keys(STATUS_LABELS) as PARequestStatus[];

/** The PA Request Tracking / Example Analyses page: a filterable queue of
 * every prior-authorization request ever drafted, across patients and
 * lifecycle statuses. Works out of the box against the seeded example PA
 * requests (see backend/scripts/seed_examples.py) -- this is the page that
 * demonstrates the real-world "track many requests over days to weeks"
 * value this app targets. See the root README's "Why LangGraph" section. */
export function TrackingPage() {
  const [patientId, setPatientId] = useState("");
  const [status, setStatus] = useState("");

  const { data: patientsData } = useQuery({ queryKey: ["patients"], queryFn: listPatients });
  const { data, isLoading } = useQuery({
    queryKey: ["pa-requests", patientId, status],
    queryFn: () => listPARequests({ patientId: patientId || undefined, status: status || undefined }),
  });

  const patientNameById = new Map(patientsData?.patients.map((p) => [p.id, p.name]) ?? []);

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <h2 className="text-xl font-semibold text-slate-900">PA request tracking</h2>
      <p className="text-sm text-slate-500">
        Every prior-authorization request ever drafted, with its current lifecycle status. Filter by patient or
        status, then open a request to see its full chart excerpt, clinical summary, criteria checklist, and
        draft form, and to update its status as it moves through the payer's review.
      </p>

      <div className="flex flex-wrap gap-3 rounded-lg border border-slate-200 bg-white p-4">
        <label className="block text-sm">
          <span className="mb-1 block text-xs font-medium text-slate-500">Patient</span>
          <select
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
            aria-label="Filter by patient"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          >
            <option value="">All patients</option>
            {patientsData?.patients.map((patient) => (
              <option key={patient.id} value={patient.id}>
                {patient.name}
              </option>
            ))}
          </select>
        </label>

        <label className="block text-sm">
          <span className="mb-1 block text-xs font-medium text-slate-500">Status</span>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            aria-label="Filter by status"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          >
            <option value="">All statuses</option>
            {ALL_STATUSES.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </label>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Loading PA requests...</p>}

      {data && data.pa_requests.length === 0 && (
        <p className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-400">
          No PA requests match these filters.
        </p>
      )}

      {data && data.pa_requests.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-xs text-slate-400">
                <th className="px-4 py-2">Chart excerpt</th>
                <th className="px-4 py-2">Patient</th>
                <th className="px-4 py-2">Payer</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Updated</th>
              </tr>
            </thead>
            <tbody>
              {data.pa_requests.map((req) => (
                <tr key={req.id} className="border-t border-slate-100">
                  <td className="px-4 py-2">
                    <Link to={`/pa-requests/${req.id}`} className="font-medium text-brand-700 hover:underline">
                      {req.original_filename}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-slate-600">{patientNameById.get(req.patient_id) ?? req.patient_id}</td>
                  <td className="px-4 py-2 text-slate-600">{req.payer_name}</td>
                  <td className="px-4 py-2">
                    <StatusBadge status={req.status} />
                  </td>
                  <td className="px-4 py-2 text-slate-400">{new Date(req.updated_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
