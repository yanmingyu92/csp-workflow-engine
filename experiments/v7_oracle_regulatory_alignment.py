"""Official FDA source mapping for the V7 oracle architecture audit.

The mappings are diagnostic. They do not assert that this research prototype
conforms to FDA guidance, operates under a validated quality system, or satisfies
any formal compliance obligation.
"""

from __future__ import annotations

from typing import Any


ACCESSED_DATE = "2026-07-25"

FDA_SOURCES: dict[str, dict[str, str]] = {
    "electronic_records_2024": {
        "title": (
            "Electronic Systems, Electronic Records, and Electronic "
            "Signatures in Clinical Investigations: Questions and Answers"
        ),
        "status": "Final guidance, October 2024; nonbinding recommendations",
        "url": (
            "https://www.fda.gov/regulatory-information/"
            "search-fda-guidance-documents/electronic-systems-electronic-"
            "records-and-electronic-signatures-clinical-investigations-questions"
        ),
    },
    "data_integrity_2018": {
        "title": (
            "Data Integrity and Compliance With Drug CGMP: " "Questions and Answers"
        ),
        "status": (
            "Final guidance, December 2018; drug CGMP scope; used here only "
            "as a data-integrity design analogy"
        ),
        "url": (
            "https://www.fda.gov/regulatory-information/"
            "search-fda-guidance-documents/data-integrity-and-compliance-"
            "drug-cgmp-questions-and-answers"
        ),
    },
    "study_data_2026": {
        "title": (
            "Study Data Technical Conformance Guide - "
            "Technical Specifications Document"
        ),
        "status": "Current technical guide, June 2026; nonbinding recommendations",
        "url": (
            "https://www.fda.gov/regulatory-information/"
            "search-fda-guidance-documents/study-data-technical-conformance-"
            "guide-technical-specifications-document"
        ),
    },
    "ai_draft_2025": {
        "title": (
            "Considerations for the Use of Artificial Intelligence To Support "
            "Regulatory Decision-Making for Drug and Biological Products"
        ),
        "status": (
            "Draft guidance, January 2025; not for implementation; scope "
            "applicability to this workflow-support context is not established"
        ),
        "url": (
            "https://www.fda.gov/regulatory-information/"
            "search-fda-guidance-documents/considerations-use-artificial-"
            "intelligence-support-regulatory-decision-making-drug-and-biological"
        ),
    },
}


ALIGNMENT_ROWS: tuple[dict[str, Any], ...] = (
    {
        "source": "electronic_records_2024",
        "principle": (
            "Use systems fit for purpose and validate them with a risk-based "
            "approach that considers intended use, data importance, impact, "
            "configuration, interfaces, and data transfers."
        ),
        "architecture_control": (
            "Frozen input configuration, immutable content hashes, deterministic "
            "unit/eval checks, and an independent artifact verifier."
        ),
        "machine_evidence": (
            "input_hashes.json; artifact_hashes.json; verification-report.md; "
            "17+ unit tests plus full-panel verifier outcomes"
        ),
        "classification": "architecture property; benchmark proxy",
        "validated_operational_control": "Not established",
        "formal_compliance": "Not established",
        "remaining_human_responsibility": (
            "Define the actual intended use and risk assessment; approve "
            "requirements, UAT, SOPs, release, incident handling, and operational "
            "validation in the deployed environment."
        ),
    },
    {
        "source": "electronic_records_2024",
        "principle": (
            "Retain records and metadata so activity is traceable and the "
            "investigation can be reconstructed; make audit-trail documentation "
            "available and review it using a justified risk-based process."
        ),
        "architecture_control": (
            "Per-run manifests record chunk identity, source/content/fragment "
            "hashes, rank, token accounting, selection reason, response hash, "
            "criterion history, and failure records."
        ),
        "machine_evidence": (
            "oracle_decomposition.json; failure_log.json; 288 unique manifest and "
            "response linkages; zero reconstruction/hash failures"
        ),
        "classification": "architecture property; benchmark proxy",
        "validated_operational_control": "Not established",
        "formal_compliance": "Not established",
        "remaining_human_responsibility": (
            "Establish authorized access, identity attribution, electronic "
            "signature controls where applicable, retention schedules, backup/"
            "restore qualification, audit-trail review, and exception approval."
        ),
    },
    {
        "source": "data_integrity_2018",
        "principle": (
            "Data should be complete, consistent, accurate, and reliable, with "
            "risk-based controls appropriate to the applicable CGMP context."
        ),
        "architecture_control": (
            "Canonical serialization, immutable hashes, preserved failures, "
            "version-conflict exclusion, and exact rerun comparison."
        ),
        "machine_evidence": (
            "byte-identical rerun hashes; V6 baseline SHA256; frozen-input hashes; "
            "version/stale/conflict metrics"
        ),
        "classification": "architecture property; benchmark proxy",
        "validated_operational_control": "Not established",
        "formal_compliance": "Not established",
        "remaining_human_responsibility": (
            "Determine whether and how the drug-CGMP guidance applies to a real "
            "deployment; own quality-system procedures, record review, deviations, "
            "CAPA, training, and data-integrity governance."
        ),
    },
    {
        "source": "study_data_2026",
        "principle": (
            "Use currently supported standards from the FDA Data Standards "
            "Catalog; state versions clearly and evaluate data against applicable "
            "conformance, business, and validator rules."
        ),
        "architecture_control": (
            "Pinned SDTM IG, ADaM IG, and Define-XML versions; explicit stale/"
            "conflict exclusion; deterministic validation criteria."
        ),
        "machine_evidence": (
            "registry standards_pins; per-manifest declared_version and "
            "version_conflicts; version_selection_correctness and "
            "version_conflict_output_correctness"
        ),
        "classification": "architecture property; benchmark proxy",
        "validated_operational_control": "Not established",
        "formal_compliance": "Not established",
        "remaining_human_responsibility": (
            "Check the current FDA Data Standards Catalog and receiving division "
            "for each actual submission; run qualified current validators; correct "
            "or explain meaningful discrepancies in the applicable reviewer guide."
        ),
    },
    {
        "source": "study_data_2026",
        "principle": (
            "Preserve provenance and traceability among analysis results, analysis "
            "datasets, tabulation datasets, source data, and derivation algorithms."
        ),
        "architecture_control": (
            "Evidence graph, chunk-level provenance, response evidence IDs, "
            "criterion-level histories, and source-to-fragment reconstruction."
        ),
        "machine_evidence": (
            "provenance_completeness; correct_citation_rate; dependency coverage; "
            "source/content/fragment hash verification"
        ),
        "classification": "architecture property; benchmark proxy",
        "validated_operational_control": "Not established",
        "formal_compliance": "Not established",
        "remaining_human_responsibility": (
            "Review semantic correctness and actual end-to-end source-to-submission "
            "lineage. A retrieved or cited skill section is not proof of traceable "
            "clinical data, derivations, or submission content."
        ),
    },
    {
        "source": "ai_draft_2025",
        "principle": (
            "For an in-scope AI context of use, define the question and context, "
            "assess model risk, plan and execute credibility assessment, document "
            "results/deviations, and judge adequacy; report suitable performance "
            "metrics and uncertainty and keep test data independent."
        ),
        "architecture_control": (
            "Predeclared frozen panel, held-out tasks, task-level uncertainty, LOO "
            "sensitivity, independent verifier, and no score-based router tuning."
        ),
        "machine_evidence": (
            "plan file; input hashes; 24-task held-out panel; bootstrap intervals; "
            "LOO ranges; claim-boundary booleans"
        ),
        "classification": "benchmark proxy",
        "validated_operational_control": "Not established",
        "formal_compliance": "Not established",
        "remaining_human_responsibility": (
            "First determine whether the draft guidance and its AI model-risk "
            "framework apply; define a real context of use, consequences, risk, "
            "acceptance criteria, monitoring, change control, and human decision "
            "authority. The draft is not for implementation."
        ),
    },
    {
        "source": "electronic_records_2024",
        "principle": (
            "Document roles, responsibilities, system/data flow, lifecycle "
            "controls, change control, validation, backup, and audit-trail review."
        ),
        "architecture_control": (
            "Human-overseen design with explicit frozen-input boundaries, "
            "machine-verifiable evidence, verifier separation, and proposals that "
            "cannot self-authorize production changes."
        ),
        "machine_evidence": (
            "claim_boundaries; graph_design_audit; independent verification; "
            "failure log; no paid generation or publish action"
        ),
        "classification": "architecture property",
        "validated_operational_control": "Not established",
        "formal_compliance": "Not established",
        "remaining_human_responsibility": (
            "Assign accountable owners and qualified reviewers; approve changes, "
            "exceptions, records, releases, and final regulatory interpretations. "
            "The system does not replace human oversight or sign-off."
        ),
    },
)
