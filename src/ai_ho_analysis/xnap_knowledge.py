"""Standards-aware XnAP knowledge for explainable handover diagnostics.

The mappings in this module are diagnostic lenses, not claims that vendor PM
counters map one-to-one to XnAP messages or Cause IE values.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

import pandas as pd

from .models import AnalysisResult


XNAP_REFERENCE = "ETSI TS 138 423 V16.9.0 / 3GPP TS 38.423 Release 16"
XNAP_URL = (
    "https://www.etsi.org/deliver/etsi_ts/138400_138499/138423/"
    "16.09.00_60/ts_138423v160900p.pdf"
)
MAPPING_CAVEAT = (
    "Standards-aligned diagnostic lens; confirm exact vendor-counter semantics "
    "with the applicable PM counter documentation and traces."
)


@dataclass(frozen=True)
class XnAPConcept:
    name: str
    section: str
    stage: str
    interpretation: str
    checks: str
    aliases: tuple[str, ...]


XNAP_CONCEPTS: tuple[XnAPConcept, ...] = (
    XnAPConcept(
        "Handover Preparation",
        "8.2.1",
        "Preparation / target admission",
        "The source sends HANDOVER REQUEST and starts TXnRELOCprep. The target either "
        "acknowledges admitted resources or returns HANDOVER PREPARATION FAILURE with a Cause IE.",
        "Correlate request, acknowledge/failure, target admission, PDU-session rejection, "
        "security compatibility, slice/QoS support, and timer expiry.",
        ("handover preparation", "handover request", "preparation failure", "prep fail"),
    ),
    XnAPConcept(
        "TXnRELOCprep",
        "8.2.1.2-8.2.1.3; 9.5",
        "Preparation timeout",
        "Maximum time allowed for Handover Preparation at the source. No target response "
        "before expiry leads the source toward Handover Cancel.",
        "Check Xn-C reachability and latency, target processing/admission load, message loss, "
        "and whether a late acknowledge/failure arrived after cancellation.",
        ("txnrelocprep", "reloc prep", "preparation timeout", "prep expiry"),
    ),
    XnAPConcept(
        "TXnRELOCoverall",
        "8.2.1.2; 8.2.7.4; 9.5",
        "Execution / completion timeout",
        "Protects the overall handover after preparation. Expiry without UE Context Release "
        "indicates that preparation completed but final mobility completion was not confirmed.",
        "Check UE target access, RRC execution, radio quality, target completion, context release, "
        "and data-forwarding continuity. Do not classify this as a preparation failure.",
        ("txnrelocoverall", "reloc overall", "overall timeout", "overall expiry"),
    ),
    XnAPConcept(
        "Handover Cancel",
        "8.2.3",
        "Cancellation",
        "The source cancels an ongoing or prepared handover and provides an appropriate cause.",
        "Separate operator/policy cancellation, partial admission, preparation timeout, and "
        "superseding mobility actions before counting the event as a radio execution failure.",
        ("handover cancel", "procedure cancelled", "cancelled handover"),
    ),
    XnAPConcept(
        "UE Context Release / Handover Success",
        "8.2.7-8.2.8",
        "Successful completion",
        "UE Context Release normally confirms handover completion and allows source resources to "
        "be released. HANDOVER SUCCESS explicitly supports CHO and DAPS completion signaling.",
        "Verify success-counter definitions against the completion event used by the vendor, and "
        "distinguish immediate HO from CHO/DAPS behavior.",
        ("handover success", "ue context release", "successful completion", "daps", "cho"),
    ),
    XnAPConcept(
        "Failure Indication",
        "8.4.7; 9.1.3.16",
        "Post-failure evidence",
        "Transfers RRC re-establishment or UE RLF-report information to a node where the UE may "
        "have suffered a connection failure.",
        "Correlate failure-cell PCI, re-establishment CGI, RRC re-establishment indicator, UE RLF "
        "report, and the preceding source-target relation.",
        ("failure indication", "rlf report", "rrc reestablishment", "re-establishment"),
    ),
    XnAPConcept(
        "Handover Report",
        "8.4.8; 9.1.3.17",
        "Mobility robustness",
        "Reports HO too early, HO to wrong cell, or inter-system ping-pong mobility problems.",
        "Use the report type and source/target/re-establishment CGI evidence before recommending "
        "trigger or neighbour changes; failure rate alone cannot identify these cases.",
        ("handover report", "ho too early", "too early", "wrong cell", "ping pong", "ping-pong"),
    ),
    XnAPConcept(
        "Mobility Settings Change",
        "8.4.9",
        "Mobility parameter coordination",
        "Peer NG-RAN nodes can negotiate handover-trigger settings; a rejected proposal returns a "
        "Cause IE and may include an allowed modification range.",
        "Use only after evidence supports a trigger problem. Validate permitted ranges and avoid "
        "automatic parameter changes based solely on aggregate counters.",
        ("mobility settings", "mobility change", "handover trigger", "trigger settings"),
    ),
)


@dataclass(frozen=True)
class XnAPCause:
    cause: str
    layer: str
    stage: str
    diagnosis: str
    checks: str
    aliases: tuple[str, ...] = ()


XNAP_CAUSES: tuple[XnAPCause, ...] = (
    XnAPCause("No Radio Resources Available in Target Cell", "Radio Network", "Preparation", "Target admission/capacity shortage.", "Review target PRB/load, admission policy, QoS demand, and time correlation.", ("no radio resources", "target congestion")),
    XnAPCause("Handover Target not Allowed", "Radio Network", "Preparation", "The requested target is prohibited for the UE.", "Check mobility restrictions, access policy, PLMN/NPN/CAG context, and target eligibility.", ("target not allowed",)),
    XnAPCause("Partial Handover", "Radio Network", "Preparation / cancellation", "The target did not admit every requested PDU session and the source elected not to proceed.", "Inspect the not-admitted PDU-session list and per-session cause before tuning radio parameters.", ("partial handover", "partial admission")),
    XnAPCause("TXnRELOCprep Expiry", "Radio Network", "Preparation timeout", "The target did not complete preparation within the source timer.", "Check Xn-C transport, target processing, admission latency, message loss, and late responses.", ("txnrelocprep", "prep expiry")),
    XnAPCause("TXnRELOCoverall Expiry", "Radio Network", "Execution / completion timeout", "The prepared handover did not complete within the overall protection timer.", "Check target access, RRC execution, RLF evidence, completion/context-release signaling, and UE return to source.", ("txnrelocoverall", "overall expiry")),
    XnAPCause("Encryption And/Or Integrity Protection Algorithms Not Supported", "Radio Network", "Preparation", "Source/UE security capabilities do not match target policy.", "Compare UE security capabilities and target allowed encryption/integrity algorithms.", ("security algorithms", "integrity algorithms", "encryption algorithms")),
    XnAPCause("Resources not available for the slice(s)", "Radio Network", "Preparation", "The target supports the feature but lacks resources for the requested slices.", "Check S-NSSAI admission, slice capacity, and rejected PDU sessions.", ("slice resources", "resources for slices")),
    XnAPCause("Slice(s) not supported by NG-RAN", "Radio Network", "Preparation", "The requested slice capability is not supported at the target.", "Validate S-NSSAI support and neighbour/slice configuration consistency.", ("slice not supported", "s-nssai not supported")),
    XnAPCause("Radio Connection With UE Lost", "Radio Network", "Execution", "Radio connectivity to the UE was lost.", "Correlate RLF report, serving/target radio quality, timing advance, interference, and re-establishment cell.", ("radio connection lost", "ue lost")),
    XnAPCause("Failure in the Radio Interface Procedure", "Radio Network", "Execution", "A radio-interface procedure failed.", "Inspect RRC failure/timeout counters and UE traces before changing mobility thresholds.", ("radio interface failure", "rrc failure")),
    XnAPCause("Transport Resource Unavailable", "Transport", "Preparation or forwarding", "Required transport resources are unavailable.", "Check Xn-C/Xn-U reachability, SCTP health, GTP-U tunnel allocation, packet loss, latency, and capacity.", ("transport unavailable", "transport resource")),
    XnAPCause("Protocol Error", "Protocol", "Signaling", "Syntax, semantic, state-compatibility, or message-construction error.", "Inspect ERROR INDICATION, Criticality Diagnostics, message sequence, software compatibility, and ASN.1 decoding.", ("transfer syntax", "semantic error", "receiver state", "protocol error")),
    XnAPCause("Control Processing Overload", "Misc", "Processing", "The node lacks control-plane processing capacity at the event time.", "Correlate CPU/control-plane load, concurrent procedures, latency, and node alarms.", ("processing overload", "control overload")),
    XnAPCause("Not enough User Plane Processing Resources", "Misc", "User plane", "The node lacks user-plane processing resources.", "Check UP utilization, tunnel/resource admission, throughput saturation, and platform alarms.", ("user plane resources", "up processing resources")),
    XnAPCause("UE Context ID not known", "Radio Network", "Context retrieval", "The old node cannot identify the requested UE context.", "Check context lifetime, UE/XnAP ID correlation, restart/reset history, and re-establishment sequence.", ("context id not known", "unknown ue context")),
)


def _normalise(text: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def _matches(query: str, label: str, aliases: Iterable[str]) -> bool:
    q = _normalise(query)
    candidates = (_normalise(label), *(_normalise(alias) for alias in aliases))
    return any(candidate and candidate in q for candidate in candidates)


def find_xnap_knowledge(query: str) -> tuple[list[XnAPConcept], list[XnAPCause]]:
    concepts = [item for item in XNAP_CONCEPTS if _matches(query, item.name, item.aliases)]
    causes = [item for item in XNAP_CAUSES if _matches(query, item.cause, item.aliases)]
    return concepts, causes


def xnap_catalog_table() -> pd.DataFrame:
    rows = [
        {
            "Topic": item.name,
            "Layer": "XnAP procedure",
            "Stage": item.stage,
            "Interpretation": item.interpretation,
            "Recommended checks": item.checks,
            "Reference": f"TS 38.423 section {item.section}",
        }
        for item in XNAP_CONCEPTS
    ]
    rows.extend(
        {
            "Topic": item.cause,
            "Layer": item.layer,
            "Stage": item.stage,
            "Interpretation": item.diagnosis,
            "Recommended checks": item.checks,
            "Reference": "TS 38.423 section 9.2.3.2",
        }
        for item in XNAP_CAUSES
    )
    return pd.DataFrame(rows)


def xnap_answer_table(query: str) -> pd.DataFrame:
    concepts, causes = find_xnap_knowledge(query)
    if not concepts and not causes:
        return xnap_catalog_table()
    rows = []
    for item in concepts:
        rows.append({"Topic": item.name, "Layer": "XnAP procedure", "Stage": item.stage, "Interpretation": item.interpretation, "Recommended checks": item.checks, "Reference": f"TS 38.423 section {item.section}"})
    for item in causes:
        rows.append({"Topic": item.cause, "Layer": item.layer, "Stage": item.stage, "Interpretation": item.diagnosis, "Recommended checks": item.checks, "Reference": "TS 38.423 section 9.2.3.2"})
    return pd.DataFrame(rows)


def kpi_protocol_lens(stage: str) -> tuple[str, str]:
    stage_key = _normalise(stage)
    if "prep" in stage_key:
        return ("Preparation/admission lens: request outcome, target admission, Cause IE, and preparation timing.", "8.2.1; 9.2.3.2; 9.5")
    if "exec" in stage_key or "failure" in stage_key:
        return ("Execution/completion lens: target access, RRC/RLF evidence, overall timing, and completion signaling.", "8.2.7-8.2.8; 8.4.7-8.4.8; 9.5")
    if "success" in stage_key:
        return ("Successful-outcome lens: confirm the vendor completion event and procedure variant (immediate HO, CHO, or DAPS).", "8.2.7-8.2.8")
    return ("Initiation-volume lens: attempts establish exposure but do not identify a failure cause.", "8.2.1")


def build_standards_diagnostics(
    ho_df: pd.DataFrame | None, result: AnalysisResult
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    detail = result.relation_detail
    attempts = float(detail.get("Attempts", pd.Series(dtype=float)).sum())
    failures = float(detail.get("Failures", pd.Series(dtype=float)).sum())
    fail_rate = failures / attempts if attempts else 0.0
    if fail_rate >= 0.05:
        rows.append({"Priority": "HIGH" if fail_rate >= 0.10 else "REVIEW", "Signal": "Elevated aggregate failure rate", "Stage": "Requires counter decomposition", "Observation": f"Global failure rate is {fail_rate:.2%}.", "Standards-aware interpretation": "Aggregate failure rate is not an XnAP cause. Split preparation, execution, transport, protocol, and cancellation evidence before action.", "Recommended validation": "Rank detailed failure counters; correlate Cause IE, timers, RLF reports, alarms, and time-of-event load.", "Reference": "TS 38.423 sections 8.2.1, 8.4.7-8.4.8, 9.2.3.2"})

    long_count = len(result.long_relations)
    if long_count:
        rows.append({"Priority": "REVIEW", "Signal": "Long-distance HO relations", "Stage": "Topology / mobility robustness", "Observation": f"{long_count} mapped relation(s) exceed the configured long-HO threshold.", "Standards-aware interpretation": "Distance is a topology heuristic, not a standardized XnAP failure cause and not proof of overshooting.", "Recommended validation": "Correlate attempts/failures with RLF reports and Handover Report types (too early, wrong cell, ping-pong), radio dominance, and neighbour design.", "Reference": "TS 38.423 sections 8.4.7-8.4.9"})

    if ho_df is not None:
        counter_rules = (
            ("prepfail", "Preparation failures", "Preparation / target admission", "Review HANDOVER PREPARATION FAILURE semantics, admission, security, QoS/slice support, and Cause IE.", "8.2.1; 9.2.3.2"),
            ("dutimeout", "DU timeout counters", "Preparation or execution timing", "Separate preparation timeout from post-preparation execution timeout; inspect signaling latency and DU processing.", "8.2.1; 9.5"),
            ("rrcto", "RRC timeout counters", "Execution / UE radio", "Correlate target access, RRC trace, RLF report, and re-establishment cell evidence.", "8.4.7-8.4.8"),
            ("tdcoverall", "Overall procedure timeout counters", "Execution / completion", "Check target completion and context-release sequence; compare with the overall-protection timer lens.", "8.2.7.4; 9.5"),
            ("cpfail", "Control-plane failure counters", "Signaling", "Inspect Xn-C/SCTP health, protocol errors, Criticality Diagnostics, sequence/state, and node load.", "9.1.3.12; 9.2.3.2"),
            ("upfail", "User-plane failure counters", "Forwarding / user plane", "Inspect Xn-U/GTP-U resources, forwarding tunnels, transport capacity, and UP processing.", "8.2.1.2; 8.2.6; 9.2.3.2"),
        )
        compact_columns = {re.sub(r"[^a-z0-9]", "", col.lower()): col for col in ho_df.columns}
        for token, signal, stage, guidance, section in counter_rules:
            matched = [original for compact, original in compact_columns.items() if token in compact]
            total = sum(float(pd.to_numeric(ho_df[col], errors="coerce").fillna(0).sum()) for col in matched)
            if total > 0:
                rows.append({"Priority": "REVIEW", "Signal": signal, "Stage": stage, "Observation": f"Observed total across matching vendor counters: {total:,.0f}.", "Standards-aware interpretation": f"{guidance} {MAPPING_CAVEAT}", "Recommended validation": "Break down by source-target relation and hour; compare PM counter definition with protocol traces before recommending changes.", "Reference": f"TS 38.423 sections {section}"})

    if result.missing_target_locations is not None and len(result.missing_target_locations):
        rows.append({"Priority": "DATA", "Signal": "Missing target coordinates", "Stage": "Data quality", "Observation": f"{len(result.missing_target_locations)} relation(s) lack target mapping.", "Standards-aware interpretation": "Distance-based mobility diagnosis is incomplete for these relations.", "Recommended validation": "Resolve target CGI/DU mapping before ranking overshooting candidates.", "Reference": "Analysis data-quality rule"})
    if not rows:
        rows.append({"Priority": "INFO", "Signal": "No dominant standards-aware signal", "Stage": "Baseline", "Observation": "The available aggregate counters do not isolate a dominant failure family.", "Standards-aware interpretation": "Additional Cause IE, timer, RLF, Handover Report, and node-alarm evidence is needed.", "Recommended validation": "Collect protocol/call-trace evidence and time-aligned radio/transport counters.", "Reference": "TS 38.423 sections 8.2, 8.4.7-8.4.9, 9.2.3.2"})
    return pd.DataFrame(rows)
