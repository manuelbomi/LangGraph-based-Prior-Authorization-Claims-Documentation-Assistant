/**
 * Hand-written TypeScript mirror of `backend/app/api/schemas.py`.
 * Keep these two files in sync when the API contract changes.
 */

export type PARequestStatus =
  | "pending"
  | "running"
  | "awaiting_staff_review"
  | "ready_to_submit"
  | "submitted"
  | "approved"
  | "denied"
  | "more_info_requested"
  | "rejected"
  | "error";

export type TrackablePAStatus = "submitted" | "approved" | "denied" | "more_info_requested";

export interface PatientSummary {
  id: string;
  name: string;
  member_id: string;
  date_of_birth: string;
  primary_payer: string;
}

export interface PARequestSummary {
  id: string;
  patient_id: string;
  payer_name: string;
  original_filename: string;
  status: PARequestStatus;
  final_status: string | null;
  created_at: string;
  updated_at: string;
}

export interface PatientDetail extends PatientSummary {
  provider_name: string;
  provider_npi: string;
  notes: string;
  pa_requests: PARequestSummary[];
}

export interface PatientListResponse {
  patients: PatientSummary[];
}

export interface PayersResponse {
  payers: string[];
}

export interface SampleDocument {
  id: string;
  label: string;
  suggested_patient_id: string | null;
  suggested_payer: string | null;
}

export interface SamplesResponse {
  samples: SampleDocument[];
}

export interface PARequestCreateResponse {
  id: string;
  patient_id: string;
  payer_name: string;
  status: PARequestStatus;
  original_filename: string;
}

export interface ClinicalSummary {
  diagnosis: string;
  requested_service: string;
  duration_of_symptoms: string;
  prior_treatments_tried: string[];
  exam_findings: string[];
  relevant_history: string[];
  referring_provider_name: string;
}

export function emptyClinicalSummary(): ClinicalSummary {
  return {
    diagnosis: "",
    requested_service: "",
    duration_of_symptoms: "",
    prior_treatments_tried: [],
    exam_findings: [],
    relevant_history: [],
    referring_provider_name: "",
  };
}

export type CriterionStatus = "met" | "unmet" | "unclear";

export interface CriterionAssessment {
  criterion_id: string;
  criterion_text: string;
  status: CriterionStatus;
  evidence: string;
}

export interface DraftForm {
  patient_name: string;
  patient_dob: string;
  patient_member_id: string;
  payer_name: string;
  provider_name: string;
  provider_npi: string;
  requested_service: string;
  service_code: string;
  diagnosis: string;
  diagnosis_code: string;
  clinical_justification: string;
}

export function emptyDraftForm(): DraftForm {
  return {
    patient_name: "",
    patient_dob: "",
    patient_member_id: "",
    payer_name: "",
    provider_name: "",
    provider_npi: "",
    requested_service: "",
    service_code: "",
    diagnosis: "",
    diagnosis_code: "",
    clinical_justification: "",
  };
}

export interface HumanDecisionRequest {
  decision: "approve" | "correct" | "reject";
  feedback: string;
  corrected_draft_form?: DraftForm | null;
  corrected_criteria_checklist?: CriterionAssessment[] | null;
}

export interface StatusUpdateRequest {
  status: TrackablePAStatus;
  note?: string;
}

export interface TraceEventOut {
  node: string;
  timestamp: string;
  summary: string;
}

export interface StatusHistoryEntry {
  status: string;
  timestamp: string;
  note: string;
}

export interface PARequestDetail extends PARequestSummary {
  clinical_summary: ClinicalSummary;
  criteria_checklist: CriterionAssessment[];
  draft_form: DraftForm;
  trace: TraceEventOut[];
  state_snapshot: Record<string, unknown>;
  status_history: StatusHistoryEntry[];
  error: string | null;
}

export interface PARequestListResponse {
  pa_requests: PARequestSummary[];
}

/** Payload of the `interrupt` SSE event -- what `staff_review_node` pauses with. */
export interface InterruptPayload {
  original_filename: string;
  clinical_summary: ClinicalSummary;
  criteria_checklist: CriterionAssessment[];
  draft_form: DraftForm;
}

/** Shapes of the SSE events emitted by GET /pa-requests/{id}/stream. */
export type StreamEvent =
  | { type: "node"; node: string; output: Record<string, unknown>; trace: TraceEventOut[] }
  | { type: "interrupt"; data: InterruptPayload }
  | { type: "done"; status: PARequestStatus; final_status: string | null }
  | { type: "error"; message: string }
  | {
      type: "replay";
      status: PARequestStatus;
      trace: TraceEventOut[];
      state_snapshot: Record<string, unknown>;
      final_status: string | null;
    };

/** The graph node names, in the order they appear in the LangGraph
 * StateGraph (backend/app/graph/graph.py). This graph is linear -- every
 * PA request visits all six nodes in this exact order. */
export const GRAPH_NODES = [
  "ingest",
  "extract_clinical_summary",
  "match_policy_criteria",
  "draft_pa_request",
  "staff_review",
  "finalize",
] as const;

export type GraphNodeName = (typeof GRAPH_NODES)[number];

export const GRAPH_NODE_LABELS: Record<GraphNodeName, string> = {
  ingest: "Ingest",
  extract_clinical_summary: "Extract Clinical Summary",
  match_policy_criteria: "Match Policy Criteria",
  draft_pa_request: "Draft PA Request",
  staff_review: "Staff Review",
  finalize: "Finalize",
};

export const STATUS_LABELS: Record<PARequestStatus, string> = {
  pending: "Pending",
  running: "Running",
  awaiting_staff_review: "Awaiting staff review",
  ready_to_submit: "Ready to submit",
  submitted: "Submitted",
  approved: "Approved",
  denied: "Denied",
  more_info_requested: "More info requested",
  rejected: "Rejected",
  error: "Error",
};
