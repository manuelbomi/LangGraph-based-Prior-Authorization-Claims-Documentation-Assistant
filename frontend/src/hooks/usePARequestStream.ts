import { useEffect, useState } from "react";

import { streamUrl } from "../api/client";
import {
  emptyClinicalSummary,
  emptyDraftForm,
  type ClinicalSummary,
  type CriterionAssessment,
  type DraftForm,
  type GraphNodeName,
  type InterruptPayload,
  type PARequestStatus,
  type TraceEventOut,
} from "../api/types";

export interface PARequestStreamState {
  status: PARequestStatus | "connecting";
  currentNode: GraphNodeName | null;
  completedNodes: GraphNodeName[];
  clinicalSummary: ClinicalSummary;
  criteriaChecklist: CriterionAssessment[];
  draftForm: DraftForm;
  trace: TraceEventOut[];
  interrupt: InterruptPayload | null;
  finalStatus: string | null;
  error: string | null;
}

const INITIAL_STATE: PARequestStreamState = {
  status: "connecting",
  currentNode: null,
  completedNodes: [],
  clinicalSummary: emptyClinicalSummary(),
  criteriaChecklist: [],
  draftForm: emptyDraftForm(),
  trace: [],
  interrupt: null,
  finalStatus: null,
  error: null,
};

const TERMINAL_STATUSES = new Set(["ready_to_submit", "rejected", "error"]);

/**
 * Subscribes to `GET /pa-requests/{id}/stream` (Server-Sent Events) and
 * folds the incoming events into a single state object a component can
 * render directly -- driving both the live GraphView highlighting and the
 * clinical-summary / criteria-checklist / draft-form output panels.
 */
export function usePARequestStream(paRequestId: string | null, generation = 0): PARequestStreamState {
  const [state, setState] = useState<PARequestStreamState>(INITIAL_STATE);

  useEffect(() => {
    if (!paRequestId) {
      setState(INITIAL_STATE);
      return;
    }

    setState({ ...INITIAL_STATE, status: "connecting" });
    const source = new EventSource(streamUrl(paRequestId));

    source.addEventListener("node", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as {
        node: GraphNodeName;
        output: Record<string, unknown>;
        trace: TraceEventOut[];
      };
      setState((prev) => ({
        ...prev,
        status: "running",
        currentNode: data.node,
        completedNodes: prev.completedNodes.includes(data.node)
          ? prev.completedNodes
          : [...prev.completedNodes, data.node],
        clinicalSummary: (data.output.clinical_summary as ClinicalSummary | undefined) ?? prev.clinicalSummary,
        criteriaChecklist:
          (data.output.criteria_checklist as CriterionAssessment[] | undefined) ?? prev.criteriaChecklist,
        draftForm: (data.output.draft_form as DraftForm | undefined) ?? prev.draftForm,
        trace: [...prev.trace, ...data.trace],
      }));
    });

    source.addEventListener("interrupt", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as InterruptPayload;
      setState((prev) => ({
        ...prev,
        status: "awaiting_staff_review",
        currentNode: "staff_review",
        completedNodes: prev.completedNodes.includes("staff_review")
          ? prev.completedNodes
          : [...prev.completedNodes, "staff_review"],
        clinicalSummary: data.clinical_summary ?? prev.clinicalSummary,
        criteriaChecklist: data.criteria_checklist ?? prev.criteriaChecklist,
        draftForm: data.draft_form ?? prev.draftForm,
        interrupt: data,
      }));
    });

    source.addEventListener("done", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as {
        status: PARequestStatus;
        final_status: string | null;
      };
      setState((prev) => ({
        ...prev,
        status: data.status,
        finalStatus: data.final_status,
        currentNode: TERMINAL_STATUSES.has(data.status) ? "finalize" : prev.currentNode,
        completedNodes:
          TERMINAL_STATUSES.has(data.status) && !prev.completedNodes.includes("finalize")
            ? [...prev.completedNodes, "finalize"]
            : prev.completedNodes,
      }));
      source.close();
    });

    source.addEventListener("replay", (evt) => {
      const data = JSON.parse((evt as MessageEvent).data) as {
        status: PARequestStatus;
        trace: TraceEventOut[];
        state_snapshot: Record<string, unknown>;
        final_status: string | null;
      };
      setState((prev) => ({
        ...prev,
        status: data.status,
        trace: data.trace,
        clinicalSummary: (data.state_snapshot.clinical_summary as ClinicalSummary | undefined) ?? prev.clinicalSummary,
        criteriaChecklist:
          (data.state_snapshot.criteria_checklist as CriterionAssessment[] | undefined) ?? prev.criteriaChecklist,
        draftForm: (data.state_snapshot.draft_form as DraftForm | undefined) ?? prev.draftForm,
        finalStatus: data.final_status,
      }));
    });

    source.addEventListener("error", (evt) => {
      // Only MessageEvents carry a backend-emitted `error` payload; a plain
      // connection failure fires this same listener with no `.data`.
      const data = (evt as MessageEvent).data;
      if (typeof data === "string") {
        const parsed = JSON.parse(data) as { message: string };
        setState((prev) => ({ ...prev, status: "error", error: parsed.message }));
        source.close();
      }
    });

    source.onerror = () => {
      setState((prev) =>
        TERMINAL_STATUSES.has(prev.status)
          ? prev
          : { ...prev, error: prev.error ?? "Connection to the PA request stream was lost." },
      );
    };

    return () => {
      source.close();
    };
    // `generation` is bumped by callers (e.g. after POST /resume) to force
    // a fresh EventSource connection against the new background task.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paRequestId, generation]);

  return state;
}
