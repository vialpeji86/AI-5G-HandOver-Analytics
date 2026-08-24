# XnAP guidance used by the local analysis agent

## Reference

- ETSI TS 138 423 V16.9.0 (2022-05)
- 3GPP TS 38.423 Release 16
- Official source: [ETSI TS 138 423 PDF](https://www.etsi.org/deliver/etsi_ts/138400_138499/138423/16.09.00_60/ts_138423v160900p.pdf)

## Knowledge included

| Agent lens | Standard area | How the agent uses it |
|---|---|---|
| Handover preparation | 8.2.1 | Separates target admission and preparation failures from execution failures. |
| `TXnRELOCprep` | 8.2.1 and 9.5 | Treats preparation expiry as a response/timing problem before target admission completes. |
| `TXnRELOCoverall` | 8.2.7 and 9.5 | Treats overall expiry as a post-preparation completion problem. |
| Handover Cancel | 8.2.3 | Avoids counting every cancellation as a UE radio execution failure. |
| UE Context Release / Handover Success | 8.2.7–8.2.8 | Validates what the vendor counts as successful completion, including CHO/DAPS cases. |
| Failure Indication | 8.4.7 | Recommends RLF and RRC re-establishment evidence for post-failure diagnosis. |
| Handover Report | 8.4.8 | Distinguishes HO too early, HO to wrong cell, and inter-system ping-pong. |
| Mobility Settings Change | 8.4.9 | Requires supporting evidence before recommending trigger changes. |
| Cause IE families | 9.2.3.2 | Organizes possible causes into radio-network, transport, protocol, and miscellaneous layers. |

## Diagnostic principles

1. Attempts measure exposure; they do not identify a failure cause.
2. Aggregate failures must be decomposed into preparation, execution/completion, transport,
   protocol, cancellation, and data-quality evidence.
3. Long source–target distance is a topology heuristic, not an XnAP cause and not proof of
   overshooting.
4. `TXnRELOCprep` and `TXnRELOCoverall` represent different stages and must not be merged into
   one generic timeout conclusion.
5. HO too early, HO to wrong cell, and ping-pong conclusions require report or trace evidence;
   a failure-rate counter alone is insufficient.
6. In Cause IE terminology, *not supported* indicates a missing capability, while
   *not available* can indicate that the capability exists but the required resource is absent.

## Important mapping limitation

Vendor PM counter names and formulas are implementation-specific. The application therefore
uses the standard as an evidence and troubleshooting framework, not as proof that a counter is
the direct measurement of an XnAP message, timer, procedure, or Cause IE. Confirm conclusions
with vendor counter documentation, protocol traces, RLF reports, and time-aligned node alarms.
