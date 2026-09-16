import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  listPatients,
  listPayers,
  listSamples,
  resumePARequest,
  runSampleReferral,
  uploadPARequest,
} from "../api/client";
import type { HumanDecisionRequest } from "../api/types";
import { GraphView } from "../components/GraphView";
import { NodePanel } from "../components/NodePanel";
import { ReviewForm } from "../components/ReviewForm";
import { usePARequestStream } from "../hooks/usePARequestStream";

const TERMINAL_STATUSES = new Set(["ready_to_submit", "rejected", "error"]);

const FINAL_STATUS_LABEL: Record<string, string> = {
  ready_to_submit: "Ready to submit",
  corrected_and_ready: "Ready to submit (edited)",
  rejected: "Rejected",
};

export function NewRequestPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [patientId, setPatientId] = useState("");
  const [payerName, setPayerName] = useState("");
  const [selectedSample, setSelectedSample] = useState("");
  const [paRequestId, setPaRequestId] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);
  const queryClient = useQueryClient();

  const { data: patientsData } = useQuery({ queryKey: ["patients"], queryFn: listPatients });
  const { data: payersData } = useQuery({ queryKey: ["payers"], queryFn: listPayers });
  const { data: samplesData } = useQuery({ queryKey: ["samples"], queryFn: listSamples });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadPARequest(file, patientId, payerName),
    onSuccess: (data) => {
      setPaRequestId(data.id);
      setGeneration(0);
    },
  });

  const sampleMutation = useMutation({
    mutationFn: (sampleId: string) => runSampleReferral(sampleId, patientId, payerName),
    onSuccess: (data) => {
      setPaRequestId(data.id);
      setGeneration(0);
    },
  });

  const stream = usePARequestStream(paRequestId, generation);

  const resumeMutation = useMutation({
    mutationFn: (payload: HumanDecisionRequest) => resumePARequest(paRequestId as string, payload),
    onSuccess: () => {
      setGeneration((g) => g + 1);
      queryClient.invalidateQueries({ queryKey: ["pa-requests"] });
      queryClient.invalidateQueries({ queryKey: ["patient", patientId] });
      queryClient.invalidateQueries({ queryKey: ["patients"] });
    },
  });

  const busy = uploadMutation.isPending || sampleMutation.isPending;
  const canStart = patientId !== "" && payerName !== "";
  const isRunActive = paRequestId !== null;

  const suggestedSamples =
    samplesData?.samples.filter((s) => s.suggested_patient_id === patientId && s.suggested_payer === payerName) ?? [];
  const otherSamples =
    samplesData?.samples.filter((s) => !(s.suggested_patient_id === patientId && s.suggested_payer === payerName)) ?? [];

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <h2 className="mb-2 text-xl font-semibold text-slate-900">New prior-authorization request</h2>
        <p className="mb-4 text-sm text-slate-500">
          Pick the patient and payer this request is for, then either upload a chart excerpt/referral or run one
          of the bundled sample referrals. The graph will extract a clinical summary, match it against the
          payer's medical-necessity criteria, draft a PA request form, then pause for staff review. Nothing is
          queued as ready to submit until staff approve it.
        </p>

        <div className="mb-4 grid gap-4 rounded-lg border border-slate-200 bg-white p-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">Patient</span>
            <select
              value={patientId}
              onChange={(e) => {
                setPatientId(e.target.value);
                setSelectedSample("");
              }}
              aria-label="Choose a patient"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Choose a patient...</option>
              {patientsData?.patients.map((patient) => (
                <option key={patient.id} value={patient.id}>
                  {patient.name} ({patient.member_id})
                </option>
              ))}
            </select>
          </label>

          <label className="block text-sm">
            <span className="mb-1 block font-medium text-slate-700">Payer</span>
            <select
              value={payerName}
              onChange={(e) => {
                setPayerName(e.target.value);
                setSelectedSample("");
              }}
              aria-label="Choose a payer"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Choose a payer...</option>
              {payersData?.payers.map((payer) => (
                <option key={payer} value={payer}>
                  {payer}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const file = fileInputRef.current?.files?.[0];
              if (file && canStart) uploadMutation.mutate(file);
            }}
            className="flex flex-col gap-3 rounded-lg border border-dashed border-slate-300 p-6"
          >
            <h3 className="text-sm font-semibold text-slate-800">Upload a chart excerpt / referral</h3>
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.txt"
              aria-label="Choose a chart excerpt to upload"
              className="text-sm"
            />
            <button
              type="submit"
              disabled={busy || !canStart}
              className="self-start rounded-md bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 disabled:opacity-50"
            >
              {uploadMutation.isPending ? "Uploading..." : "Upload & process"}
            </button>
            {!canStart && <p className="text-xs text-slate-400">Choose a patient and payer first.</p>}
            {uploadMutation.isError && (
              <p className="text-sm text-rose-600">{(uploadMutation.error as Error).message}</p>
            )}
          </form>

          <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-6">
            <h3 className="text-sm font-semibold text-slate-800">Or run a bundled sample referral</h3>
            <p className="text-xs text-slate-500">
              Zero-setup demo referrals bundled with this repo (see <code>sample-data/README.md</code>). Any
              sample can be run for any patient/payer, but samples matching the selection are listed first.
            </p>
            <select
              value={selectedSample}
              onChange={(e) => setSelectedSample(e.target.value)}
              aria-label="Choose a sample referral"
              className="rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">Choose a sample referral...</option>
              {suggestedSamples.length > 0 && (
                <optgroup label="Suggested for this patient/payer">
                  {suggestedSamples.map((sample) => (
                    <option key={sample.id} value={sample.id}>
                      {sample.label}
                    </option>
                  ))}
                </optgroup>
              )}
              <optgroup label={suggestedSamples.length > 0 ? "Other samples" : "All samples"}>
                {otherSamples.map((sample) => (
                  <option key={sample.id} value={sample.id}>
                    {sample.label}
                  </option>
                ))}
              </optgroup>
            </select>
            <button
              type="button"
              disabled={busy || !selectedSample || !canStart}
              onClick={() => sampleMutation.mutate(selectedSample)}
              className="self-start rounded-md bg-slate-800 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-slate-900 disabled:opacity-50"
            >
              {sampleMutation.isPending ? "Starting..." : "Run sample referral"}
            </button>
            {!canStart && <p className="text-xs text-slate-400">Choose a patient and payer first.</p>}
            {sampleMutation.isError && (
              <p className="text-sm text-rose-600">{(sampleMutation.error as Error).message}</p>
            )}
          </div>
        </div>
      </div>

      {isRunActive && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-slate-900">Live run</h3>
            <p className="text-sm text-slate-500">
              Status:{" "}
              <span className="font-medium text-slate-700">
                {stream.status === "connecting" ? "connecting..." : stream.status.replace(/_/g, " ")}
              </span>
              {stream.finalStatus && (
                <span className="ml-2 text-slate-500">
                  &middot; {FINAL_STATUS_LABEL[stream.finalStatus] ?? stream.finalStatus}
                </span>
              )}
            </p>
          </div>

          {stream.error && <p className="rounded-md bg-rose-50 p-3 text-sm text-rose-700">{stream.error}</p>}

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <GraphView currentNode={stream.currentNode} completedNodes={stream.completedNodes} />
            <NodePanel
              clinicalSummary={stream.clinicalSummary}
              criteriaChecklist={stream.criteriaChecklist}
              draftForm={stream.draftForm}
              trace={stream.trace}
            />
          </div>

          {stream.status === "awaiting_staff_review" && stream.interrupt && (
            <ReviewForm
              interrupt={stream.interrupt}
              submitting={resumeMutation.isPending}
              onDecision={(decision) => resumeMutation.mutate(decision)}
            />
          )}

          {TERMINAL_STATUSES.has(stream.status) && paRequestId && (
            <p className="rounded-md bg-slate-100 p-3 text-sm text-slate-600">
              Done.{" "}
              <Link to={`/pa-requests/${paRequestId}`} className="font-medium text-brand-700 hover:underline">
                View this request in PA Request Tracking
              </Link>
              .
            </p>
          )}
        </div>
      )}
    </div>
  );
}
