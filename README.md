# LangGraph Tutorial 05: Prior-Authorization & Claims Documentation Assistant

A [LangGraph](https://langchain-ai.github.io/langgraph/)-powered assistant
that drafts prior-authorization (PA) request paperwork from a clinician's
chart excerpt/referral: it extracts the relevant clinical facts, matches
them against a payer's published medical-necessity criteria, and assembles
a filled draft PA form -- all currently manual, repetitive, per-payer
paperwork that is one of the most notorious administrative burdens in US
healthcare.

This is part of a tutorial series building small, production-shaped
LangGraph applications:

1. `langgraph-tutorial-01-research-report-assistant`
2. `langgraph-tutorial-02-invoice-audit-reconciliation`
3. `langgraph-tutorial-03-tax-document-intake`
4. `langgraph-tutorial-04-clinical-documentation-assistant`
5. **`langgraph-tutorial-05-prior-authorization-assistant`** (this repo)

---

## Scope & Safety -- read this first

**This application is strictly an administrative documentation assistant.
It does NOT make coverage or medical-necessity decisions, and it does NOT
provide medical advice or diagnose.**

- It never diagnoses a condition, recommends a treatment, or offers medical
  advice of any kind.
- It never decides whether a requested service is covered or medically
  necessary. **Coverage and medical-necessity determinations belong solely
  to the patient's health plan (payer).** The criteria checklist this app
  produces is explicitly labeled a **draft assessment for staff review**,
  not a decision.
- It only extracts and structures information a referring clinician has
  **already written** in their chart excerpt, and only assembles paperwork
  from that information -- the extraction prompt is explicitly constrained
  to never infer, guess, or add new clinical content.
- Procedure/drug and diagnosis codes are chosen only from a small, fixed,
  non-hallucinatable reference list (`app/tools/code_reference.py`) --
  never invented.
- **Every draft PA request (the clinical summary, the criteria checklist,
  and the drafted form) must be explicitly reviewed and approved by a
  licensed staff member/clinician** via the mandatory `staff_review` step
  before it is ever considered ready to submit. Nothing is submitted to a
  payer automatically -- this app doesn't even have a "submit" button; a
  human submits it and then records that fact via the tracking endpoint.
- **All data in this repository is entirely synthetic and fictitious.**
  There is no real patient, no real clinician, no real payer, and no real
  protected health information (PHI) anywhere in this repo. The payer
  "policies" used for criteria matching are invented, plausible-sounding
  policies and do **not** represent any real insurance company's actual
  medical policy. See `sample-data/README.md` for exactly what was
  invented and why.

This system prompt language is embedded directly in the seeded LLM prompts
(see `backend/app/prompts/seed_prompts.py`):

> "You are a prior-authorization paperwork assistant for a clinical
> practice. You help clinical and administrative staff prepare
> prior-authorization documentation faster. You do not diagnose,
> recommend treatment, or offer medical advice, and you do not decide
> whether a service is covered or medically necessary -- that
> determination belongs to the patient's health plan (payer). Everything
> you produce is a draft for a licensed staff member or clinician to
> review, correct, and approve before anything is submitted to a payer."

The frontend also displays a persistent "administrative documentation
assistance only, not a coverage decision" banner on every page, and a
second, more detailed safety banner on the staff review screen itself.

---

## What the app does

```mermaid
flowchart TD
    START([Upload / select chart excerpt]) --> INGEST[ingest\nextract raw text from PDF/TXT]
    INGEST --> EXTRACT[extract_clinical_summary\nLLM: diagnosis, requested service,\nduration, prior treatments, exam findings]
    EXTRACT --> MATCH[match_policy_criteria\nMilvus Lite semantic search vs. payer policy\n+ LLM met/unmet/unclear assessment]
    MATCH --> DRAFT[draft_pa_request\nLLM: assemble draft PA form\n+ codes from fixed reference list]
    DRAFT --> REVIEW{{staff_review\ninterrupt -- SAFETY GATE}}
    REVIEW -->|approve / edit / reject| FINALIZE[finalize\nmark ready_to_submit or rejected]
    FINALIZE --> TRACK[Status tracking\nsubmitted -> approved / denied / more info requested]
    TRACK --> END([PA request lifecycle])

    style REVIEW fill:#fef3c7,stroke:#d97706,stroke-width:2px
    style MATCH fill:#eef4fc,stroke:#265d9c,stroke-width:1px
```

Six real graph nodes, run per PA request (one LangGraph thread per
request), plus a separate lightweight status-tracking mechanism after the
graph completes:

1. **ingest** -- accepts an uploaded chart excerpt/referral (`.pdf` via
   `pdfplumber`, or `.txt`), extracts raw text.
2. **extract_clinical_summary** -- an LLM call (`gpt-4o-mini` by default)
   extracts a structured clinical summary: diagnosis, requested
   service/procedure/medication, duration of symptoms, prior treatments
   tried, exam findings, and relevant history -- constrained to only
   structure what the referring clinician actually wrote.
3. **match_policy_criteria** -- semantic search (a local, embedded
   **Milvus Lite** collection, no server/Docker container needed) against
   the selected payer's medical-necessity criteria for the requested
   service, filtered to that payer. A second LLM call then assesses each
   retrieved criterion as **met / unmet / unclear**, citing evidence quoted
   from the chart -- explicitly labeled a **draft assessment for staff
   review**, never a coverage decision.
4. **draft_pa_request** -- assembles a filled draft PA request form:
   trusted patient/provider/payer identifiers (looked up from Postgres, not
   generated by the LLM), a procedure/drug code and diagnosis code chosen
   by a third LLM call from a small **fixed reference list** (never
   invented), and a clinical justification narrative referencing which
   criteria appear met.
5. **staff_review** (LangGraph `interrupt()`) -- **the mandatory safety
   gate.** Presents the clinical summary, criteria checklist, and draft
   form for a staff member to edit and Approve / Edit & Approve / Reject.
   Nothing is finalized without this step.
6. **finalize** -- records the staff decision: `ready_to_submit` (or
   `corrected_and_ready`) if approved, `rejected` otherwise. This is a
   **drafting outcome only** -- it does not submit anything to a payer.
7. **Status tracking (`POST /pa-requests/{id}/status`)** -- a simple,
   separate field update (not a graph re-entry) that lets staff record the
   request's real-world progress over the following days to weeks:
   `ready_to_submit -> submitted -> approved / denied / more_info_requested`
   (and `more_info_requested -> submitted` again after a resubmission).

---

## Why LangGraph specifically: durable checkpointing + mandatory human review

Prior authorization is exactly the kind of workflow that punishes anything
built as a single in-memory request/response flow:

- A staff member's PA review queue doesn't get worked through in one
  sitting -- referrals trickle in throughout the day, and staff may not
  open a given request for review until hours or days later. **Nothing
  here should ever be auto-submitted to a payer.** LangGraph's
  `interrupt()` combined with the Postgres-backed checkpointer
  (`AsyncPostgresSaver`) is exactly the right fit: every request's graph
  run pauses durably at `staff_review`, with the full state (raw chart
  text, clinical summary, criteria checklist, draft form) persisted to
  Postgres, not held in server memory. The FastAPI process can restart or
  redeploy, and a request can simply sit untouched in a queue for as long
  as needed; when staff come back (even from an entirely new process),
  `Command(resume=...)` against the same `thread_id` picks up exactly
  where it left off. This is proven end-to-end by
  `backend/tests/live/test_live_smoke.py`, which tears down and rebuilds
  the checkpointer + graph between the interrupt and the resume, simulating
  staff returning to their queue in a fresh process.
- A prior-authorization request's real-world lifecycle genuinely spans
  **days to weeks** after drafting is done: it gets submitted, then the
  payer takes its own time to respond with approved / denied / more info
  requested, sometimes cycling back to "submitted" after a resubmission.
  That's not something a single graph run should model as more LLM steps
  in a loop -- it's genuinely just state that needs to persist reliably
  per-request over a long window. This app models it as a small, durable
  Postgres row (`pa_requests.status` + `status_history`) updated via a
  plain API call, while the LangGraph-and-LLM-backed drafting pipeline
  handles the one-time-per-request work of turning a chart into a defensible
  draft. Together, this is what makes the "PA Request Tracking" page useful
  for many patients' requests in parallel, at different points in that
  lifecycle, without needing to re-run any LLM step just to check status.

This mirrors the same durable-human-in-the-loop pattern used in
`langgraph-tutorial-03-tax-document-intake` and
`langgraph-tutorial-04-clinical-documentation-assistant`, applied here to a
workflow where both the correctness bar for what's drafted and the
real-world duration of the process are higher.

---

## Sample data / zero-setup demo

Everything needed for a working out-of-the-box demo is bundled and
entirely synthetic -- see `sample-data/README.md` for full provenance:

- `sample-data/referrals/` -- 4 synthetic chart excerpts/referrals (plain
  text): a lumbar MRI referral with criteria clearly met, a specialty
  medication (biologic) request with criteria met, a physical therapy
  extension request with a mixed/unclear outcome, and a second lumbar MRI
  referral submitted too early (criteria mostly unmet) -- deliberately
  varied so the criteria-matching step demonstrates all three outcomes.
- `sample-data/payer-policies/` -- 3 fictitious payer medical-necessity
  policy documents (plain text, one per payer/service), each listing a
  small set of lettered criteria in a simple parseable format. These are
  embedded into a local Milvus Lite collection at startup.
- `sample-data/patients/` -- 4 fictitious patients, each with a primary
  payer and a referring provider name/NPI.
- `sample-data/pa-form-template/` -- a blank, generic, payer-agnostic PA
  request form template describing the target field structure.

On first boot (`docker-entrypoint.sh`, or the manual steps below), the
backend runs migrations, seeds the three LLM prompts, embeds the payer
policy criteria into Milvus Lite, loads the four fictitious patients, and
seeds 4 already-drafted example PA requests spanning different lifecycle
statuses (`ready_to_submit`, `submitted`, `more_info_requested`,
`rejected`). You can then either upload your own `.pdf`/`.txt` chart
excerpt, or run one of the bundled sample referrals end-to-end (including
the live staff-review step) straight from the "New PA Request" page.

---

## Repo structure

```
langgraph-tutorial-05-prior-authorization-assistant/
├── backend/            FastAPI + LangGraph app (Python 3.11+)
│   ├── app/
│   │   ├── api/        REST + SSE routers (patients, pa-requests)
│   │   ├── db/         SQLAlchemy models, session, Postgres checkpointer, Alembic migrations
│   │   ├── graph/       LangGraph state, pydantic schemas, nodes, graph assembly
│   │   ├── prompts/     Postgres-backed prompt registry + v1 seed prompts
│   │   └── tools/       Chart ingestion (PDF/TXT), Milvus Lite payer-policy lookup, fixed code reference table
│   ├── scripts/         seed_patients.py, seed_examples.py
│   └── tests/           Mocked unit/flow/API tests + tests/live/ (real OpenAI + Postgres)
├── frontend/           Vite + React 18 + TypeScript + Tailwind
│   └── src/
│       ├── api/         Typed API client (mirrors backend/app/api/schemas.py)
│       ├── components/  GraphView (reactflow), ReviewForm (human-in-the-loop), StatusBadge, output cards
│       ├── hooks/        usePARequestStream (SSE)
│       └── pages/        New PA Request, PA Request Tracking, PA Request Detail
├── sample-data/        Synthetic referrals, payer policies, fictitious patients, form template
├── docker-compose.yml  postgres + backend + frontend (Milvus Lite is embedded, no extra container)
└── .github/workflows/ci.yml
```

---

## Prompt registry

All three LLM prompts (`extract_clinical_summary`, `evaluate_policy_criteria`,
`draft_pa_request`) live in the Postgres `prompts` table, versioned, with
exactly one `is_active` version per name at a time
(`backend/app/prompts/registry.py`). Seed or roll a new version with:

```bash
cd backend
python -m app.prompts.seed_prompts
```

or call `app.prompts.registry.add_prompt_version(name, new_template)` to
add and activate a new version programmatically (e.g. from a script or an
admin-only route) without redeploying code.

---

## Setup & run

### Option A: Docker Compose (recommended)

```bash
cp .env.example .env   # fill in OPENAI_API_KEY
docker compose up --build
```

- Frontend: http://localhost:8080
- Backend API: http://localhost:8000 (docs at `/docs`)
- Postgres: localhost:5432

Milvus Lite is **embedded** (a local file under the backend's `/app/data`
volume) -- there is no separate Milvus container, matching the pattern used
in `langgraph-tutorial-01-research-report-assistant` and
`langgraph-tutorial-04-clinical-documentation-assistant`.

### Option B: Local dev (no Docker)

Requires a local/reachable Postgres. **Note:** `pymilvus[milvus_lite]`'s
native binary is published for Linux/macOS only -- on native Windows,
`match_policy_criteria` will gracefully degrade to an empty criteria
checklist (it catches the import/connection failure and returns an empty
list, and skips the criteria-evaluation LLM call entirely) rather than
crashing; run the backend via Docker or WSL on Windows if you need working
criteria matching locally.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp ../.env.example ../.env   # edit as needed; also copy to backend/.env if you prefer per-service env files
alembic upgrade head
python -m app.prompts.seed_prompts
python -m app.tools.policy_kb   # embeds sample-data/payer-policies/*.txt into Milvus Lite
python -m scripts.seed_patients
python -m scripts.seed_examples
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

### Running tests

```bash
# Backend -- mocked unit/flow/API tests (no real API calls, no live Postgres)
cd backend && pytest -v

# Backend -- REAL end-to-end smoke test (real OpenAI calls + real Postgres)
export OPENAI_API_KEY=sk-...
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/prior_auth
pytest -m live tests/live/test_live_smoke.py -v -s

# Frontend
cd frontend
npm run typecheck
npm run build
npm run test
```

---

## License

MIT License, Copyright (c) 2026 Emmanuel Oyekanlu. See [`LICENSE`](./LICENSE).
