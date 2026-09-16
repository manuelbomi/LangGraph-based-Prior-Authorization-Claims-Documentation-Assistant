import type { DraftForm } from "../api/types";

interface DraftFormCardProps {
  form: DraftForm;
}

const hasContent = (form: DraftForm): boolean => Boolean(form.patient_name || form.requested_service);

/** Renders the drafted prior-authorization request form. This is
 * administrative paperwork assistance only -- it does not represent a
 * coverage or medical-necessity determination, and it is not final until a
 * licensed staff member/clinician reviews and approves it. See the root
 * README's Scope & Safety section. */
export function DraftFormCard({ form }: DraftFormCardProps) {
  if (!hasContent(form)) {
    return null;
  }

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 text-sm">
      <h4 className="text-xs font-semibold uppercase text-slate-500">Draft PA request form</h4>

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        <div>
          <div className="text-xs font-medium text-slate-500">Patient</div>
          <div>{form.patient_name}</div>
        </div>
        <div>
          <div className="text-xs font-medium text-slate-500">Date of birth</div>
          <div>{form.patient_dob}</div>
        </div>
        <div>
          <div className="text-xs font-medium text-slate-500">Member ID</div>
          <div>{form.patient_member_id}</div>
        </div>
        <div>
          <div className="text-xs font-medium text-slate-500">Payer</div>
          <div>{form.payer_name}</div>
        </div>
        <div>
          <div className="text-xs font-medium text-slate-500">Provider</div>
          <div>{form.provider_name}</div>
        </div>
        <div>
          <div className="text-xs font-medium text-slate-500">Provider NPI</div>
          <div>{form.provider_npi}</div>
        </div>
        <div>
          <div className="text-xs font-medium text-slate-500">Requested service</div>
          <div>{form.requested_service}</div>
        </div>
        <div>
          <div className="text-xs font-medium text-slate-500">Procedure/drug code</div>
          <div className="font-mono">{form.service_code || "--"}</div>
        </div>
        <div>
          <div className="text-xs font-medium text-slate-500">Diagnosis</div>
          <div>{form.diagnosis}</div>
        </div>
        <div>
          <div className="text-xs font-medium text-slate-500">Diagnosis code</div>
          <div className="font-mono">{form.diagnosis_code || "--"}</div>
        </div>
      </div>

      <div>
        <div className="mb-1 text-xs font-medium text-slate-500">Clinical justification (draft)</div>
        <p className="whitespace-pre-wrap text-slate-700">{form.clinical_justification}</p>
      </div>
    </div>
  );
}
