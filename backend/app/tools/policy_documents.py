"""Parses the fictitious payer policy `.txt` files under
`sample-data/payer-policies/` into individual criterion chunks ready to
embed into Milvus Lite.

Each policy file follows a small, deliberately simple format (see
`sample-data/README.md` and any file in `payer-policies/` for an example):

    PAYER: <payer name>
    SERVICE: <service description>
    POLICY TITLE: <title>

    CRITERION a: <criterion text>
    CRITERION b: <criterion text>
    ...

This keeps the sample policy documents themselves human-readable plain
text (real provenance a reader can open and check), while still giving the
seeding code a trivial, dependency-free way to turn them into individually
embeddable/citable chunks -- one Milvus row per lettered criterion, each
tagged with its payer and service for filtered semantic search.
"""
from __future__ import annotations

import glob
import os
import re
from dataclasses import dataclass

_CRITERION_RE = re.compile(r"^CRITERION\s+([a-zA-Z0-9]+)\s*:\s*(.+)$")


@dataclass
class PolicyCriterionChunk:
    criterion_id: str  # e.g. "meridian-lumbar-mri-a"
    payer_name: str
    service: str
    policy_title: str
    criterion_label: str  # e.g. "a"
    text: str


def _parse_one(path: str) -> list[PolicyCriterionChunk]:
    payer_name = ""
    service = ""
    policy_title = ""
    criteria: list[tuple[str, str]] = []

    with open(path, encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if line.startswith("PAYER:"):
                payer_name = line[len("PAYER:") :].strip()
            elif line.startswith("SERVICE:"):
                service = line[len("SERVICE:") :].strip()
            elif line.startswith("POLICY TITLE:"):
                policy_title = line[len("POLICY TITLE:") :].strip()
            else:
                match = _CRITERION_RE.match(line)
                if match:
                    criteria.append((match.group(1), match.group(2).strip()))

    if not payer_name or not service or not criteria:
        raise ValueError(
            f"{path}: expected PAYER:, SERVICE:, and at least one CRITERION line"
        )

    slug_base = re.sub(r"[^a-z0-9]+", "-", payer_name.lower()).strip("-")
    return [
        PolicyCriterionChunk(
            criterion_id=f"{slug_base}-{label}",
            payer_name=payer_name,
            service=service,
            policy_title=policy_title,
            criterion_label=label,
            text=text,
        )
        for label, text in criteria
    ]


def load_policy_chunks(sample_data_dir: str) -> list[PolicyCriterionChunk]:
    """Parse every `*.txt` file in `sample-data/payer-policies/` into a flat
    list of per-criterion chunks."""
    policy_dir = os.path.join(sample_data_dir, "payer-policies")
    paths = sorted(glob.glob(os.path.join(policy_dir, "*.txt")))
    if not paths:
        raise SystemExit(f"No payer policy files found in {policy_dir!r}")

    chunks: list[PolicyCriterionChunk] = []
    for path in paths:
        chunks.extend(_parse_one(path))
    return chunks
