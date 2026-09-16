import type {
  HumanDecisionRequest,
  PARequestCreateResponse,
  PARequestDetail,
  PARequestListResponse,
  PatientDetail,
  PatientListResponse,
  PayersResponse,
  SamplesResponse,
  StatusUpdateRequest,
} from "./types";

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

export async function listPatients(): Promise<PatientListResponse> {
  const res = await fetch(`${API_BASE_URL}/patients`);
  return handle<PatientListResponse>(res);
}

export async function getPatient(patientId: string): Promise<PatientDetail> {
  const res = await fetch(`${API_BASE_URL}/patients/${encodeURIComponent(patientId)}`);
  return handle<PatientDetail>(res);
}

export async function listPayers(): Promise<PayersResponse> {
  const res = await fetch(`${API_BASE_URL}/pa-requests/payers`);
  return handle<PayersResponse>(res);
}

export async function listSamples(): Promise<SamplesResponse> {
  const res = await fetch(`${API_BASE_URL}/pa-requests/samples`);
  return handle<SamplesResponse>(res);
}

export async function runSampleReferral(
  sampleId: string,
  patientId: string,
  payerName: string,
): Promise<PARequestCreateResponse> {
  const formData = new FormData();
  formData.append("patient_id", patientId);
  formData.append("payer_name", payerName);
  const res = await fetch(`${API_BASE_URL}/pa-requests/samples/${encodeURIComponent(sampleId)}/run`, {
    method: "POST",
    body: formData,
  });
  return handle<PARequestCreateResponse>(res);
}

export async function uploadPARequest(
  file: File,
  patientId: string,
  payerName: string,
): Promise<PARequestCreateResponse> {
  const formData = new FormData();
  formData.append("patient_id", patientId);
  formData.append("payer_name", payerName);
  formData.append("file", file);
  const res = await fetch(`${API_BASE_URL}/pa-requests/upload`, { method: "POST", body: formData });
  return handle<PARequestCreateResponse>(res);
}

export async function resumePARequest(
  paRequestId: string,
  payload: HumanDecisionRequest,
): Promise<PARequestCreateResponse> {
  const res = await fetch(`${API_BASE_URL}/pa-requests/${encodeURIComponent(paRequestId)}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<PARequestCreateResponse>(res);
}

export async function listPARequests(params?: {
  patientId?: string;
  status?: string;
}): Promise<PARequestListResponse> {
  const query = new URLSearchParams();
  if (params?.patientId) query.set("patient_id", params.patientId);
  if (params?.status) query.set("status", params.status);
  const qs = query.toString();
  const res = await fetch(`${API_BASE_URL}/pa-requests${qs ? `?${qs}` : ""}`);
  return handle<PARequestListResponse>(res);
}

export async function getPARequest(paRequestId: string): Promise<PARequestDetail> {
  const res = await fetch(`${API_BASE_URL}/pa-requests/${encodeURIComponent(paRequestId)}`);
  return handle<PARequestDetail>(res);
}

export async function updatePARequestStatus(
  paRequestId: string,
  payload: StatusUpdateRequest,
): Promise<PARequestDetail> {
  const res = await fetch(`${API_BASE_URL}/pa-requests/${encodeURIComponent(paRequestId)}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handle<PARequestDetail>(res);
}

export function streamUrl(paRequestId: string): string {
  return `${API_BASE_URL}/pa-requests/${encodeURIComponent(paRequestId)}/stream`;
}

export function paRequestFileUrl(paRequestId: string): string {
  return `${API_BASE_URL}/pa-requests/${encodeURIComponent(paRequestId)}/file`;
}
