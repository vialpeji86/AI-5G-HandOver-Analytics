from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class KPIDef:
    name: str
    formula: str
    domain: str  # Intra or Inter
    stage: str   # Attempt, Prep, Exec, Success, Failure
    category: str
    meaning: str


KPI_DEFS: List[KPIDef] = [
    KPIDef("EndcIntraChgPrepFail_MenbFail_per_GNB", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGPREPFAI_MENBFAIGNB", "Intra", "Prep", "Failure", "Preparation failure caused by MeNB-side issue before HO execution."),
    KPIDef("EndcIntraChgFail_DuTimeout_per_GNB", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGFAIL_DUTIMEOUT_GNB", "Intra", "Exec", "Failure", "Execution failure due to DU timeout during HO procedure."),
    KPIDef("EndcIntraChgPrepSucc_per_GNB", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGPREPSUCC_GNB", "Intra", "Prep", "Success", "Successful HO preparation at source side before final execution."),
    KPIDef("EndcIntraChgPrepFail_DuFail_per_GNB", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGPREPFAIL_DUFAI_GNB", "Intra", "Prep", "Failure", "Preparation failure due to DU processing/rejection issue."),
    KPIDef("EndcIntraChgFail_MenbFail_per_GNB", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGFAIL_MENBFAIL_GNB", "Intra", "Exec", "Failure", "Execution failure caused by MeNB issue."),
    KPIDef("EndcIntraChgPrepFail_CpFail_per_GNB", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGPRPFAI_CPFAI_GNB", "Intra", "Prep", "Failure", "Preparation failure in control-plane signaling phase."),
    KPIDef("EndcIntraChgPrepFail_DuTimeout", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGPREPFAIL_DUTIMEOUT", "Intra", "Prep", "Failure", "Preparation failure due to DU response timeout."),
    KPIDef("EndcIntraChgFail_RrcTo_per_GNB", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGFAIL_RRCTO_PER_GNB", "Intra", "Exec", "Failure", "Execution failure because RRC procedure timed out."),
    KPIDef("EndcIntraChgSucc_per_GNB", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGSUCC_PER_GNB", "Intra", "Exec", "Success", "End-to-end successful Intra-EN-DC change completion."),
    KPIDef("EndcIntraChgAtt_per_GNB", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGATT_PER_GNB", "Intra", "Attempt", "Volume", "Total Intra-EN-DC HO attempts initiated."),
    KPIDef("EndcIntraChgPrepFail_UpFail_per_GNB", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGPREPFAIL_UPFAI_GNB", "Intra", "Prep", "Failure", "Preparation failure caused by user-plane setup issue."),
    KPIDef("EndcIntraChgFail_Tdcoverall_per_GNB", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGFAIL_TDCOVERAL_GNB", "Intra", "Exec", "Failure", "Execution failure linked to TDC/overall timing/resource condition."),
    KPIDef("EndcIntraChgFail_CpFail_per_GNB", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGFAIL_CPFAIL_GNB", "Intra", "Exec", "Failure", "Execution failure in control-plane signaling."),
    KPIDef("EndcIntraChgPrepFail_UpTimeout", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGPREPFAIL_UPTIMEOUT", "Intra", "Prep", "Failure", "Preparation failure due to user-plane timeout."),
    KPIDef("EndcIntraChgFail_UpFail_per_GNB", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGFAIL_UPFAIL_GNB", "Intra", "Exec", "Failure", "Execution failure due to user-plane issue."),
    KPIDef("EndcIntraChgFail_DuFail_per_GNB", "S5NC_INTRA_SN_PSCEL_CHG_GNB:ENDCINTRACHGFAIL_DUFAIL_GNB", "Intra", "Exec", "Failure", "Execution failure due to DU failure/rejection."),

    KPIDef("EndcInterChgSrcPrepFail_MenbFail", "S5NC_INT_PSEL_CNG_SRC_GNB:ENDCINTERCHGSRCPRPFAIL_MNBFAIL", "Inter", "Prep", "Failure", "Inter-source preparation failure caused by MeNB issue."),
    KPIDef("EndcInterChgSrcFail_Tdcoverall_per_GNB", "S5NC_INT_PSEL_CNG_SRC_GNB:ENDCINTERCHGSRCFAI_TDCOVRL_GNB", "Inter", "Exec", "Failure", "Inter-source execution failure linked to TDC/overall condition."),
    KPIDef("EndcInterChgSrcFail_DuFail_per_GNB", "S5NC_INT_PSEL_CNG_SRC_GNB:ENDCINTERCHGSRCFAIL_DUFAIGNB", "Inter", "Exec", "Failure", "Inter-source execution failure due to DU issue."),
    KPIDef("EndcInterChgSrcPrepFail_CpFail_per_GNB", "S5NC_INT_PSEL_CNG_SRC_GNB:ENDCINTERCHGSRCPRPFAI_CPFAIGNB", "Inter", "Prep", "Failure", "Inter-source preparation CP signaling failure."),
    KPIDef("EndcInterChgSrcFail_UpFail_per_GNB", "S5NC_INT_PSEL_CNG_SRC_GNB:ENDCINTERCHGSRCFAI_UPFAI_PRGNB", "Inter", "Exec", "Failure", "Inter-source execution failure due to user-plane issue."),
    KPIDef("EndcInterChgSrcFail_DuTimeout_per_GNB", "S5NC_INT_PSEL_CNG_SRC_GNB:ENDCINTERCHGSRCFAIL_DUTIMT_GNB", "Inter", "Exec", "Failure", "Inter-source execution failure due to DU timeout."),
    KPIDef("EndcInterChgSrcSucc_per_GNB", "S5NC_INT_PSEL_CNG_SRC_GNB:ENDCINTERCHGSRCSUCC_PER_GNB", "Inter", "Exec", "Success", "Successful Inter-source EN-DC change completion."),
    KPIDef("EndcInterChgSrcPrepFail_DuFail_per_GNB", "S5NC_INT_PSEL_CNG_SRC_GNB:ENDCINTERCHGSRCPREFAI_DUFAIGNB", "Inter", "Prep", "Failure", "Inter-source preparation failure due to DU issue."),
    KPIDef("EndcInterChgSrcFail_UpTimeout_per_GNB", "S5NC_INT_PSEL_CNG_SRC_GNB:ENDCINTERCHGSRCFAIL_UPTMT_GNB", "Inter", "Exec", "Failure", "Inter-source execution failure due to user-plane timeout."),
    KPIDef("EndcInterChgSrcPrepFail_UpFail_per_GNB", "S5NC_INT_PSEL_CNG_SRC_GNB:ENDCINTERCHGSRCPREFAI_UPFAIGNB", "Inter", "Prep", "Failure", "Inter-source preparation failure due to user-plane issue."),
    KPIDef("EndcInterChgSrcPrepSucc_per_GNB", "S5NC_INT_PSEL_CNG_SRC_GNB:ENDCINTERCHGSRCPREPSUCC_GNB", "Inter", "Prep", "Success", "Successful Inter-source HO preparation phase."),
    KPIDef("EndcInterChgSrcFail_MenbFail_per_GNB", "S5NC_INT_PSEL_CNG_SRC_GNB:ENDCINTERCHGSRCFAI_MENBFAIGNB", "Inter", "Exec", "Failure", "Inter-source execution failure caused by MeNB issue."),
    KPIDef("EndcInterChgSrcAtt_per_GNB", "S5NC_INT_PSEL_CNG_SRC_GNB:ENDCINTERCHGSRCATT_PER_GNB", "Inter", "Attempt", "Volume", "Total Inter-source EN-DC change attempts initiated."),
]

KPI_INDEX: Dict[str, KPIDef] = {k.name.lower(): k for k in KPI_DEFS}


def find_kpi_matches(query: str) -> List[KPIDef]:
    q = query.lower()
    q_compact = "".join(ch for ch in q if ch.isalnum())
    # Exact or near-exact KPI-name match first
    exact: List[KPIDef] = []
    for k in KPI_DEFS:
        name = k.name.lower()
        name_compact = "".join(ch for ch in name if ch.isalnum())
        if name in q or name_compact in q_compact:
            exact.append(k)
    if exact:
        return exact[:10]

    direct = [k for k in KPI_DEFS if k.name.lower() in q]
    if direct:
        return direct

    # Token-based soft matches for terms like "dutimeout" or "prep fail menb"
    hits: List[KPIDef] = []
    for k in KPI_DEFS:
        s = k.name.lower()
        score = 0
        for token in ["intra", "inter", "prep", "succ", "att", "fail", "dutimeout", "dufail", "uptimeout", "upfail", "menbfail", "cpfail", "rrcto", "tdcoverall"]:
            if token in q and token in s:
                score += 1
        if score >= 2:
            hits.append(k)
    return hits[:10]
