# Sample data

**Everything in this folder is entirely synthetic and fictitious.** The
patients (Jordan Blake, Casey Rivera, Morgan Ellis, Sam Okafor), the
providers and clinics (Cedar Valley Family Medicine, Riverbend Rheumatology
Associates, Summit Orthopedic Physical Therapy), the payers (Meridian
Health Plan, Cascade Community Health, Beacon Preferred Insurance), the
member IDs, dates, and all clinical details (symptoms, exam findings,
treatments tried, lab values) were invented for this repository. **No real
patient, no real clinician, no real payer, and no real medical record was
used or referenced in any way. The payer policies below are invented
plausible-sounding policies and do not represent the actual medical
policy of any real insurance company.**

This app is an **administrative documentation assistant that drafts
prior-authorization paperwork. It does not make coverage or
medical-necessity decisions** (that is the payer's decision) **and does
not provide medical advice or diagnose.** Every draft it produces must be
reviewed and approved by a licensed staff member/clinician before
submission. See the root `README.md` "Scope & Safety" section.

## What's here

### `referrals/` -- 4 synthetic clinical referral / chart excerpts (plain text)

Plain `.txt` files (the ingest node also supports `.pdf`, extracted with
`pdfplumber` -- the bundled samples are plain text purely for
readability/diffability in a git repo). Each describes a fictitious
scenario needing prior authorization, deliberately varied so the
criteria-matching step produces different outcomes:

| File | Patient | Payer | Requested service | Expected criteria outcome |
|---|---|---|---|---|
| `lumbar_mri_referral_jordan_blake.txt` | Jordan Blake | Meridian Health Plan | Lumbar spine MRI | Mostly **met** -- 10 weeks of pain, failed PT/NSAIDs, neuro deficit present |
| `specialty_medication_adalimumab_casey_rivera.txt` | Casey Rivera | Cascade Community Health | Adalimumab (biologic) | Mostly **met** -- confirmed diagnosis, failed methotrexate, active disease, screening done |
| `pt_extension_request_morgan_ellis.txt` | Morgan Ellis | Beacon Preferred Insurance | Physical therapy extension | **Mixed / unclear** -- clear functional improvement, but the most recent visit note is incomplete |
| `lumbar_mri_referral_sam_okafor.txt` | Sam Okafor | Meridian Health Plan | Lumbar spine MRI | Mostly **unmet** -- only 12 days of symptoms, no conservative treatment attempted yet |

Two of these (Jordan Blake, Casey Rivera) are pre-processed and seeded
into the database (see `backend/scripts/seed_examples.py`) so the "PA
Request Tracking" page has real example analyses across different
statuses out of the box. All four are available in the app's "run a
bundled sample" picker for a live, zero-setup demo of the full graph
(including the mandatory staff review step).

### `payer-policies/` -- 3 fictitious payer medical-necessity policy documents

Plain `.txt` files, one per (fictitious payer, service) pair, each listing
a small set of lettered medical-necessity criteria in a simple, parseable
format (`CRITERION a: ...`, `CRITERION b: ...`). These are the documents
the app treats as its payer knowledge base:

- `meridian_lumbar_mri_policy.txt` -- Meridian Health Plan, lumbar spine MRI
- `cascade_specialty_medication_policy.txt` -- Cascade Community Health, adalimumab for psoriatic arthritis
- `beacon_physical_therapy_extension_policy.txt` -- Beacon Preferred Insurance, physical therapy extension

At startup, `backend/app/tools/policy_kb.py` parses these files and embeds
each individual criterion as its own chunk into a local **Milvus Lite**
collection (`payer_policy_criteria`), tagged with its payer name and
service. The `match_policy_criteria` graph node semantically searches this
collection (filtered to the request's selected payer) to retrieve the
relevant criteria, then asks an LLM to assess each one as met / unmet /
unclear against the chart excerpt -- explicitly labeled everywhere as a
**draft assessment for staff review, not a coverage or medical-necessity
determination**. See the root README's Scope & Safety section.

### `patients/` -- 4 fictitious patient records (JSON)

Loaded into the `patients` table by `backend/scripts/seed_patients.py`.
Each is a minimal fictitious identity (name, member ID, date of birth,
primary payer, referring provider name/NPI) with no real-world
correspondence. NPIs are made-up 10-digit numbers, not registered to any
real provider.

### `pa-form-template/prior_authorization_request_form_template.txt`

A blank, generic, payer-agnostic prior-authorization request form
template -- the target field structure (patient/provider/payer info,
requested service + procedure/drug code, diagnosis + ICD-10-style code,
clinical justification narrative, and a mandatory staff sign-off section)
that the `draft_pa_request` graph node fills in. It is not a copy of any
real payer's actual form.

## Regenerating / extending

There's nothing to auto-generate here -- these are hand-authored plain-text
referrals and hand-authored fictitious policy documents. To add another
sample referral, drop a new `.txt`/`.pdf` file in `referrals/`, add an
entry to `SAMPLE_CATALOG` in `backend/app/api/routers/pa_requests.py`, and
optionally add a pre-baked example via `backend/scripts/seed_examples.py`.
To add another payer/service policy, drop a new `PAYER: / SERVICE: /
CRITERION a: ...` formatted `.txt` file in `payer-policies/` -- the parser
in `backend/app/tools/policy_kb.py` picks up any file matching that format
automatically.
