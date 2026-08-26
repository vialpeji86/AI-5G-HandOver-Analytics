from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from .configuration import AnalysisConfig
from .models import AnalysisResult
from .schema_inference import HOSchemaMapping, apply_ho_mapping, infer_ho_schema


class HOAnalyzer:
    HO_ATT_COLS = ["EndcIntraChgAtt_per_GNB", "Attempts", "ATTEMPTS"]
    HO_SUCC_COLS = ["EndcIntraChgSucc_per_GNB", "Success", "SUCCESS"]

    def __init__(self, config: AnalysisConfig | None = None) -> None:
        self.config = config or AnalysisConfig()
        self.ho_df: Optional[pd.DataFrame] = None
        self.map_df: Optional[pd.DataFrame] = None
        self.ho_mapping: Optional[HOSchemaMapping] = None
        self.last_result: Optional[AnalysisResult] = None

    def set_ho_data(self, df: pd.DataFrame, mapping: Optional[HOSchemaMapping] = None) -> None:
        self.ho_df = df.copy()
        self.ho_mapping = mapping
        self.last_result = None

    def set_map_data(self, df: pd.DataFrame) -> None:
        self.map_df = df.copy()
        self.last_result = None

    def upsert_manual_location(self, du_full: int, lat: float, lon: float) -> None:
        """Insert or update one manual DU location (11-digit GNB+DU)."""
        if self.map_df is None or self.map_df.empty:
            self.map_df = pd.DataFrame({"DU": [du_full], "LAT": [lat], "LON": [lon]})
            return

        mp = self.map_df.copy()
        low = {c.lower(): c for c in mp.columns}
        if all(k in low for k in ["du", "lat", "lon"]):
            du_col = low["du"]
            lat_col = low["lat"]
            lon_col = low["lon"]
            du_num = pd.to_numeric(mp[du_col].astype(str).str.replace(r"\D", "", regex=True), errors="coerce")
            idx = du_num[du_num == int(du_full)].index
            if len(idx):
                mp.loc[idx, lat_col] = float(lat)
                mp.loc[idx, lon_col] = float(lon)
            else:
                mp = pd.concat(
                    [mp, pd.DataFrame([{du_col: int(du_full), lat_col: float(lat), lon_col: float(lon)}])],
                    ignore_index=True,
                )
        elif all(k in low for k in ["gnbduid", "lat", "lon"]):
            gnbdu_col = low["gnbduid"]
            lat_col = low["lat"]
            lon_col = low["lon"]
            gnbdu_num = pd.to_numeric(mp[gnbdu_col], errors="coerce")
            idx = gnbdu_num[gnbdu_num == int(du_full)].index
            if len(idx):
                mp.loc[idx, lat_col] = float(lat)
                mp.loc[idx, lon_col] = float(lon)
            else:
                new_row = {gnbdu_col: int(du_full), lat_col: float(lat), lon_col: float(lon)}
                if "sectorid" in low:
                    new_row[low["sectorid"]] = np.nan
                if "carrierid" in low:
                    new_row[low["carrierid"]] = np.nan
                mp = pd.concat([mp, pd.DataFrame([new_row])], ignore_index=True)
        else:
            # Fallback: convert to DU/LAT/LON minimal format
            mp = pd.DataFrame({"DU": [du_full], "LAT": [lat], "LON": [lon]})

        self.map_df = mp

    def _pick_col(self, df: pd.DataFrame, options: list[str]) -> Optional[str]:
        for c in options:
            if c in df.columns:
                return c
        low = {x.lower(): x for x in df.columns}
        for c in options:
            if c.lower() in low:
                return low[c.lower()]
        return None

    def _to_num(self, df: pd.DataFrame, cols: list[str]) -> None:
        for c in cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

    def _normalize_full_du_series(self, s: pd.Series) -> pd.Series:
        # Keep only digits to handle values like "2419283-3325" or text-wrapped IDs.
        cleaned = s.astype(str).str.replace(r"\D", "", regex=True)
        return pd.to_numeric(cleaned, errors="coerce")

    def _haversine_km(
        self, lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray
    ) -> np.ndarray:
        r = 6371.0
        lat1r = np.radians(lat1)
        lon1r = np.radians(lon1)
        lat2r = np.radians(lat2)
        lon2r = np.radians(lon2)
        dlat = lat2r - lat1r
        dlon = lon2r - lon1r
        a = np.sin(dlat / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlon / 2) ** 2
        return 2 * r * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    @staticmethod
    def _identifier_series(df: pd.DataFrame, columns: list[str], fallback: str) -> pd.Series:
        usable = [column for column in columns if column in df.columns]
        if not usable:
            return pd.Series([fallback] * len(df), index=df.index, dtype="string")
        parts = [df[column].astype("string").fillna("").str.strip() for column in usable]
        result = parts[0]
        for part in parts[1:]:
            result = result.str.cat(part, sep="|")
        return result.str.strip("|").replace("", fallback)

    def _build_failure_views(
        self,
        detail: pd.DataFrame,
        failure_columns: list[str],
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        failure_columns = [column for column in failure_columns if column in detail.columns]
        identity_columns = [
            column
            for column in (
                "Source_ID",
                "Source_Site",
                "Target_ID",
                "Target_Site",
                "Date_Start",
                "Date_End",
                "Observed_Days",
                "Attempts",
                "Failures",
                "Fail_Rate",
                "Distance_km",
            )
            if column in detail.columns
        ]
        if not failure_columns:
            empty = pd.DataFrame()
            return empty, empty, empty, empty

        failure_detail = detail.melt(
            id_vars=identity_columns,
            value_vars=failure_columns,
            var_name="Failure_Type",
            value_name="Failure_Count",
        )
        failure_detail["Failure_Count"] = pd.to_numeric(
            failure_detail["Failure_Count"], errors="coerce"
        ).fillna(0)
        failure_detail = failure_detail[failure_detail["Failure_Count"] > 0].sort_values(
            ["Failure_Count", "Failures"], ascending=[False, False]
        )

        if failure_detail.empty:
            empty = pd.DataFrame()
            return empty, failure_detail, empty, empty

        total_failures = float(failure_detail["Failure_Count"].sum())
        failure_types = (
            failure_detail.groupby("Failure_Type", as_index=False)
            .agg(
                Total_Failures=("Failure_Count", "sum"),
                Affected_Relations=("Failure_Count", "size"),
                Affected_Sources=("Source_ID", "nunique"),
                Affected_Targets=("Target_ID", "nunique"),
            )
            .sort_values("Total_Failures", ascending=False)
        )
        failure_types["Failure_Share"] = np.where(
            total_failures > 0,
            failure_types["Total_Failures"] / total_failures,
            np.nan,
        )

        def offender_view(group_column: str, peer_column: str, site_column: str) -> pd.DataFrame:
            aggregation: dict[str, tuple[str, Any]] = {
                "Total_Failures": ("Failures", "sum"),
                "Relations": (peer_column, "size"),
                "Unique_Peers": (peer_column, "nunique"),
            }
            if "Attempts" in detail.columns:
                aggregation["Attempts"] = ("Attempts", "sum")
            if site_column in detail.columns:
                aggregation[site_column] = (site_column, "first")
            offenders = detail.groupby(group_column, as_index=False).agg(**aggregation)
            if "Attempts" in offenders.columns:
                offenders["Fail_Rate"] = np.where(
                    offenders["Attempts"] > 0,
                    offenders["Total_Failures"] / offenders["Attempts"],
                    np.nan,
                )

            by_type = (
                failure_detail.groupby([group_column, "Failure_Type"], as_index=False)[
                    "Failure_Count"
                ]
                .sum()
                .sort_values("Failure_Count", ascending=False)
            )
            dominant = by_type.drop_duplicates(group_column).rename(
                columns={
                    "Failure_Type": "Dominant_Failure_Type",
                    "Failure_Count": "Dominant_Failure_Count",
                }
            )
            type_count = (
                by_type.groupby(group_column, as_index=False)["Failure_Type"]
                .nunique()
                .rename(columns={"Failure_Type": "Failure_Type_Count"})
            )
            offenders = offenders.merge(dominant, on=group_column, how="left").merge(
                type_count, on=group_column, how="left"
            )
            return offenders.sort_values(
                ["Total_Failures", "Unique_Peers"], ascending=[False, False]
            )

        source_offenders = offender_view("Source_ID", "Target_ID", "Source_Site")
        target_offenders = offender_view("Target_ID", "Source_ID", "Target_Site")
        return failure_types, failure_detail, source_offenders, target_offenders

    def _generic_map_coordinates(self, relation: pd.DataFrame) -> pd.DataFrame:
        relation = relation.copy()
        for column in ("src_lat", "src_lon", "tgt_lat", "tgt_lon"):
            relation[column] = np.nan
        if self.map_df is None or self.map_df.empty:
            return relation

        mp = self.map_df.copy()
        lower = {str(column).casefold(): column for column in mp.columns}
        lat_col = next((lower[key] for key in ("lat", "latitude") if key in lower), None)
        lon_col = next((lower[key] for key in ("lon", "longitude", "lng") if key in lower), None)
        id_col = next(
            (
                lower[key]
                for key in ("du", "gnbduid", "cell_id", "cellid", "site_name", "site")
                if key in lower
            ),
            None,
        )
        if not (id_col and lat_col and lon_col):
            return relation

        def normalized_id(series: pd.Series) -> pd.Series:
            return series.astype("string").fillna("").str.replace(r"\W", "", regex=True).str.upper()

        lookup = pd.DataFrame(
            {
                "__ID": normalized_id(mp[id_col]),
                "__Lat": pd.to_numeric(mp[lat_col], errors="coerce"),
                "__Lon": pd.to_numeric(mp[lon_col], errors="coerce"),
            }
        ).dropna(subset=["__Lat", "__Lon"])
        lookup = lookup[lookup["__ID"] != ""].drop_duplicates("__ID", keep=False)
        src_lookup = lookup.rename(
            columns={"__ID": "__Source_Key", "__Lat": "src_lat_map", "__Lon": "src_lon_map"}
        )
        tgt_lookup = lookup.rename(
            columns={"__ID": "__Target_Key", "__Lat": "tgt_lat_map", "__Lon": "tgt_lon_map"}
        )
        relation["__Source_Key"] = normalized_id(relation["Source_ID"])
        relation["__Target_Key"] = normalized_id(relation["Target_ID"])
        relation = relation.merge(src_lookup, on="__Source_Key", how="left").merge(
            tgt_lookup, on="__Target_Key", how="left"
        )
        relation["src_lat"] = relation["src_lat_map"]
        relation["src_lon"] = relation["src_lon_map"]
        relation["tgt_lat"] = relation["tgt_lat_map"]
        relation["tgt_lon"] = relation["tgt_lon_map"]
        return relation.drop(
            columns=[
                "__Source_Key",
                "__Target_Key",
                "src_lat_map",
                "src_lon_map",
                "tgt_lat_map",
                "tgt_lon_map",
            ]
        )

    def _run_generic(self, ho: pd.DataFrame, mapping: HOSchemaMapping) -> AnalysisResult:
        prepared = apply_ho_mapping(ho, mapping)
        prepared = prepared[(prepared["__Source_ID"] != "") & (prepared["__Target_ID"] != "")]
        if prepared.empty:
            raise ValueError("No rows contain both mapped Source and Target values.")

        prepared["Failures"] = prepared[mapping.failure_columns].sum(axis=1)
        if mapping.source_cell:
            prepared["__Source_ID"] = self._identifier_series(
                prepared, [mapping.source, mapping.source_cell], "UNKNOWN_SOURCE"
            )
        if mapping.target_cell:
            prepared["__Target_ID"] = self._identifier_series(
                prepared, [mapping.target, mapping.target_cell], "UNKNOWN_TARGET"
            )
        group_columns = ["__Source_ID", "__Target_ID"]
        known_dimensions = {
            "GNB": "Source_GNB",
            "DU": "Source_DU",
            "SECTOR": "Source_Sector",
            "CARRIER": "Source_Carrier",
            "TGTGNB": "Target_GNB",
            "TGTDU": "Target_DU",
            "TGTSECTOR": "Target_Sector",
            "TGTCARRIER": "Target_Carrier",
            "ENODEB": "Source_ENODEB",
            "EUTRANCELL": "Source_Cell",
            "ENODEB_TARGET": "Target_ENODEB",
            "CELL_TARGET": "Target_Cell",
            "NEIGHBORCELL": "Neighbor_Cell",
        }
        for original, canonical in known_dimensions.items():
            if original in prepared.columns:
                prepared[canonical] = prepared[original]
                group_columns.append(canonical)
        if {"GNB", "DU"}.issubset(prepared.columns):
            prepared["__Source_ID"] = self._identifier_series(
                prepared, ["GNB", "DU"], "UNKNOWN_SOURCE"
            )
        if {"TGTGNB", "TGTDU"}.issubset(prepared.columns):
            prepared["__Target_ID"] = self._identifier_series(
                prepared, ["TGTGNB", "TGTDU"], "UNKNOWN_TARGET"
            )
        if {"ENODEB", "EUTRANCELL"}.issubset(prepared.columns):
            prepared["__Source_ID"] = self._identifier_series(
                prepared, ["ENODEB", "EUTRANCELL"], "UNKNOWN_SOURCE"
            )
        if {"ENODEB_TARGET", "CELL_TARGET"}.issubset(prepared.columns):
            prepared["__Target_ID"] = self._identifier_series(
                prepared, ["ENODEB_TARGET", "CELL_TARGET"], "UNKNOWN_TARGET"
            )
        optional_mapping = {
            "source_site": "Source_Site",
            "target_site": "Target_Site",
            "source_cell": "Source_Cell",
            "target_cell": "Target_Cell",
        }
        for role, canonical in optional_mapping.items():
            original = getattr(mapping, role)
            if original:
                prepared[canonical] = prepared[original].astype("string")
                if canonical not in group_columns:
                    group_columns.append(canonical)

        numeric_columns = [*mapping.failure_columns, "Failures"]
        if mapping.attempts:
            numeric_columns.append("__Attempts")
        if mapping.success:
            numeric_columns.append("__Success")
        relation = prepared.groupby(group_columns, dropna=False, as_index=False)[numeric_columns].sum()
        if mapping.date:
            date_summary = (
                prepared.groupby(group_columns, dropna=False, as_index=False)["__Date"]
                .agg(["min", "max", "nunique"])
                .reset_index()
                .rename(
                    columns={
                        "min": "Date_Start",
                        "max": "Date_End",
                        "nunique": "Observed_Days",
                    }
                )
            )
            relation = relation.merge(date_summary, on=group_columns, how="left")
        relation = relation.rename(
            columns={
                "__Source_ID": "Source_ID",
                "__Target_ID": "Target_ID",
                "__Attempts": "Attempts",
                "__Success": "Success",
            }
        )
        if "Attempts" not in relation.columns:
            relation["Attempts"] = np.nan
        if "Success" not in relation.columns:
            relation["Success"] = np.nan
        relation["Fail_Rate"] = np.where(
            relation["Attempts"] > 0,
            relation["Failures"] / relation["Attempts"],
            np.nan,
        )
        relation["Success_Rate"] = np.where(
            relation["Attempts"] > 0,
            relation["Success"] / relation["Attempts"],
            np.nan,
        )
        relation = self._generic_map_coordinates(relation)
        mask = relation[["src_lat", "src_lon", "tgt_lat", "tgt_lon"]].notna().all(axis=1)
        relation["Distance_km"] = np.nan
        relation.loc[mask, "Distance_km"] = self._haversine_km(
            relation.loc[mask, "src_lat"].to_numpy(float),
            relation.loc[mask, "src_lon"].to_numpy(float),
            relation.loc[mask, "tgt_lat"].to_numpy(float),
            relation.loc[mask, "tgt_lon"].to_numpy(float),
        )
        relation["Distance_Band"] = pd.cut(
            relation["Distance_km"],
            bins=[-0.001, 1, 3, 5, 10, np.inf],
            labels=["0-1km", "1-3km", "3-5km", "5-10km", ">10km"],
        )
        relation = relation.sort_values(["Failures", "Attempts"], ascending=[False, False])

        mapped = relation[relation["Distance_km"].notna()].copy()
        missing_target = relation[relation["tgt_lat"].isna() | relation["tgt_lon"].isna()].copy()
        total_attempts = pd.to_numeric(relation["Attempts"], errors="coerce").sum(min_count=1)
        total_failures = float(relation["Failures"].sum())
        summary = pd.DataFrame(
            [
                ["Total HO Relations", len(relation)],
                ["Mapped Relations", len(mapped)],
                ["Mapped Coverage", len(mapped) / len(relation) if len(relation) else np.nan],
                ["Relations Missing Target Location", len(missing_target)],
                ["Total Attempts", total_attempts],
                ["Total Failures", total_failures],
                [
                    "Global Fail Rate",
                    total_failures / total_attempts
                    if pd.notna(total_attempts) and total_attempts > 0
                    else np.nan,
                ],
                ["Detected Failure Types", len(mapping.failure_columns)],
            ],
            columns=["KPI", "Value"],
        )
        top_failures = relation.head(self.config.top_relations)
        long_relations = relation[relation["Distance_km"] > self.config.long_handover_km]
        distance_bands = (
            mapped.groupby("Distance_Band", observed=False, as_index=False)
            .agg(Relations=("Failures", "size"), Failures=("Failures", "sum"))
            .sort_values("Distance_Band")
        )
        long_ho_table = relation[relation["Distance_km"] >= self.config.review_handover_km]
        failure_types, failure_detail, source_offenders, target_offenders = (
            self._build_failure_views(relation, mapping.failure_columns)
        )
        result = AnalysisResult(
            summary=summary,
            relation_detail=relation,
            top_failures=top_failures,
            long_relations=long_relations,
            distance_bands=distance_bands,
            missing_target_locations=missing_target,
            long_ho_table=long_ho_table,
            failure_types=failure_types,
            failure_detail=failure_detail,
            source_offenders=source_offenders,
            target_offenders=target_offenders,
        )
        self.last_result = result
        return result

    def run(self) -> AnalysisResult:
        if self.ho_df is None:
            raise ValueError("HO dataset is not loaded.")

        ho = self.ho_df.copy()
        required = ["DU", "SECTOR", "CARRIER", "TGTDU", "TGTSECTOR", "TGTCARRIER"]
        has_structured_schema = all(column in ho.columns for column in required)
        if not has_structured_schema or self.map_df is None:
            mapping = self.ho_mapping or infer_ho_schema(ho).mapping
            return self._run_generic(ho, mapping)

        mp = self.map_df.copy()

        missing = [c for c in required if c not in ho.columns]
        if missing:
            raise ValueError(f"HO file is missing required columns: {missing}")

        att_col = self._pick_col(ho, self.HO_ATT_COLS)
        succ_col = self._pick_col(ho, self.HO_SUCC_COLS)
        if not att_col:
            raise ValueError("Could not find attempts KPI column in HO data.")

        fail_cols = [
            c for c in ho.columns if c.startswith("EndcIntraChg") and ("Fail" in c or "Timeout" in c)
        ]
        if not fail_cols:
            fail_cols = [c for c in ho.columns if "fail" in c.lower()]

        optional_ids = [c for c in ["GNB", "TGTGNB"] if c in ho.columns]
        self._to_num(ho, required + optional_ids + [att_col] + ([succ_col] if succ_col else []) + fail_cols)

        ho["Attempts"] = ho[att_col].fillna(0)
        ho["Success"] = ho[succ_col].fillna(0) if succ_col else 0
        ho["Failures"] = ho[fail_cols].fillna(0).sum(axis=1) if fail_cols else 0

        dims = ["DU", "SECTOR", "CARRIER", "TGTDU", "TGTSECTOR", "TGTCARRIER"]
        for c in ["DUNAME", "SITE"]:
            if c in ho.columns:
                dims.append(c)
        if "GNB" in ho.columns:
            dims.append("GNB")
        if "TGTGNB" in ho.columns:
            dims.append("TGTGNB")
        relation_value_columns = ["Attempts", "Success", *fail_cols]
        relation = ho.groupby(dims, as_index=False)[relation_value_columns].sum()
        relation["Failures"] = relation[fail_cols].sum(axis=1) if fail_cols else 0
        date_col = self._pick_col(ho, ["DAY", "DATE", "Date", "Timestamp"])
        if date_col:
            ho["__Date"] = pd.to_datetime(ho[date_col], errors="coerce")
            date_summary = (
                ho.groupby(dims, dropna=False, as_index=False)["__Date"]
                .agg(["min", "max", "nunique"])
                .reset_index()
                .rename(
                    columns={
                        "min": "Date_Start",
                        "max": "Date_End",
                        "nunique": "Observed_Days",
                    }
                )
            )
            relation = relation.merge(date_summary, on=dims, how="left")

        relation["Fail_Rate"] = np.where(
            relation["Attempts"] > 0, relation["Failures"] / relation["Attempts"], np.nan
        )
        relation["Success_Rate"] = np.where(
            relation["Attempts"] > 0, relation["Success"] / relation["Attempts"], np.nan
        )

        # Coordinates mapping supports:
        # 1) Legacy: gnbduid + sectorid + carrierid + Lat + Lon
        # 2) DU full: DU(11 digits) + LAT + LON
        cols_lower = {c.lower(): c for c in mp.columns}
        has_legacy = all(k in cols_lower for k in ["gnbduid", "sectorid", "carrierid", "lat", "lon"])
        has_du_full = all(k in cols_lower for k in ["du", "lat", "lon"])

        if not has_legacy and not has_du_full:
            raise ValueError(
                "Coordinates file format not recognized. Expected either "
                "[gnbduid, sectorid, carrierid, Lat, Lon] or [DU, LAT, LON]."
            )

        if has_legacy:
            mp = mp.rename(
                columns={
                    cols_lower["gnbduid"]: "DU_FULL",
                    cols_lower["sectorid"]: "SECTOR",
                    cols_lower["carrierid"]: "CARRIER",
                    cols_lower["lat"]: "Lat",
                    cols_lower["lon"]: "Lon",
                }
            )
            # Optional metadata
            if "site name" in cols_lower:
                mp = mp.rename(columns={cols_lower["site name"]: "SITE_NAME"})
            if "market" in cols_lower:
                mp = mp.rename(columns={cols_lower["market"]: "MARKET"})

            self._to_num(mp, ["DU_FULL", "SECTOR", "CARRIER", "Lat", "Lon"])
            mp["DU"] = mp["DU_FULL"] % 10000
            mp["GNB"] = (mp["DU_FULL"] // 10000).astype("Int64")

            map_use = mp.dropna(subset=["DU", "SECTOR", "CARRIER", "Lat", "Lon"]).copy()
            key = ["DU", "SECTOR", "CARRIER"]
            unique = map_use.groupby(key).size().reset_index(name="n").query("n == 1")[key]
            map_use = map_use.merge(unique, on=key, how="inner")

            src = map_use.rename(
                columns={
                    "Lat": "src_lat",
                    "Lon": "src_lon",
                    "SITE_NAME": "Source_Site",
                    "MARKET": "Source_Market",
                    "GNB": "Source_GNB",
                }
            )[["DU", "SECTOR", "CARRIER", "src_lat", "src_lon", "Source_Site", "Source_Market", "Source_GNB"]]

            tgt = map_use.rename(
                columns={
                    "DU": "TGTDU",
                    "SECTOR": "TGTSECTOR",
                    "CARRIER": "TGTCARRIER",
                    "Lat": "tgt_lat",
                    "Lon": "tgt_lon",
                    "SITE_NAME": "Target_Site",
                    "MARKET": "Target_Market",
                    "GNB": "Target_GNB",
                }
            )[[
                "TGTDU",
                "TGTSECTOR",
                "TGTCARRIER",
                "tgt_lat",
                "tgt_lon",
                "Target_Site",
                "Target_Market",
                "Target_GNB",
            ]]

            merged = relation.merge(src, on=["DU", "SECTOR", "CARRIER"], how="left").merge(
                tgt, on=["TGTDU", "TGTSECTOR", "TGTCARRIER"], how="left"
            )
        else:
            # DU full format: DU = 11 digits (7 gNodeB + 4 DU)
            rename_map = {
                cols_lower["du"]: "DU_FULL",
                cols_lower["lat"]: "Lat",
                cols_lower["lon"]: "Lon",
            }
            for alias in ("site_name", "site name", "site"):
                if alias in cols_lower:
                    rename_map[cols_lower[alias]] = "SITE_NAME"
                    break
            if "market" in cols_lower:
                rename_map[cols_lower["market"]] = "MARKET"
            mp = mp.rename(columns=rename_map)
            mp["DU_FULL"] = self._normalize_full_du_series(mp["DU_FULL"])
            self._to_num(mp, ["Lat", "Lon"])
            mp = mp.dropna(subset=["DU_FULL", "Lat", "Lon"]).copy()
            mp["DU"] = (mp["DU_FULL"] % 10000).astype("Int64")
            mp["GNB"] = (mp["DU_FULL"] // 10000).astype("Int64")
            generated_site = "SYNTH-DU-" + mp["DU_FULL"].astype("Int64").astype(str)
            if "SITE_NAME" in mp.columns:
                mp["SITE_NAME"] = mp["SITE_NAME"].fillna(generated_site).astype(str)
            else:
                mp["SITE_NAME"] = generated_site
            if "MARKET" not in mp.columns:
                mp["MARKET"] = np.nan

            # HO DU/TGTDU can arrive as 4-digit DU or full 11-digit.
            # Preferred unique key is always GNB+DU from HO input when GNB/TGTGNB are present.
            if "GNB" in relation.columns:
                relation["SRC_DU_FULL"] = np.where(
                    relation["DU"] >= 10000000,
                    relation["DU"],
                    relation["GNB"] * 10000 + (relation["DU"] % 10000),
                )
            else:
                relation["SRC_DU_FULL"] = np.where(
                    relation["DU"] >= 10000000, relation["DU"], np.nan
                )
            if "TGTGNB" in relation.columns:
                relation["TGT_DU_FULL"] = np.where(
                    relation["TGTDU"] >= 10000000,
                    relation["TGTDU"],
                    relation["TGTGNB"] * 10000 + (relation["TGTDU"] % 10000),
                )
            else:
                relation["TGT_DU_FULL"] = np.where(
                    relation["TGTDU"] >= 10000000, relation["TGTDU"], np.nan
                )
            relation["SRC_DU_4"] = relation["DU"] % 10000
            relation["TGT_DU_4"] = relation["TGTDU"] % 10000
            relation["Source_GNB"] = np.where(
                relation["SRC_DU_FULL"].notna(),
                (relation["SRC_DU_FULL"] // 10000).astype("Int64"),
                pd.NA,
            )
            relation["Target_GNB"] = np.where(
                relation["TGT_DU_FULL"].notna(),
                (relation["TGT_DU_FULL"] // 10000).astype("Int64"),
                pd.NA,
            )

            # Exact 11-digit mapping (preferred, deterministic)
            mp_full = (
                mp[["DU_FULL", "Lat", "Lon", "SITE_NAME", "MARKET", "GNB"]]
                .drop_duplicates(subset=["DU_FULL"], keep="first")
                .rename(
                    columns={
                        "DU_FULL": "DU_FULL_KEY",
                        "Lat": "lat_full",
                        "Lon": "lon_full",
                        "SITE_NAME": "site_full",
                        "MARKET": "market_full",
                        "GNB": "gnb_full",
                    }
                )
            )
            src_full = mp_full.rename(
                columns={
                    "DU_FULL_KEY": "SRC_DU_FULL",
                    "lat_full": "src_lat_full",
                    "lon_full": "src_lon_full",
                    "site_full": "Source_Site_full",
                    "market_full": "Source_Market_full",
                    "gnb_full": "Source_GNB_full",
                }
            )
            tgt_full = mp_full.rename(
                columns={
                    "DU_FULL_KEY": "TGT_DU_FULL",
                    "lat_full": "tgt_lat_full",
                    "lon_full": "tgt_lon_full",
                    "site_full": "Target_Site_full",
                    "market_full": "Target_Market_full",
                    "gnb_full": "Target_GNB_full",
                }
            )

            # Safe fallback by DU4 only when DU4 exists once globally (no ambiguity).
            # This is only used when exact GNB+DU match is unavailable.
            du4_count = mp.groupby("DU").size().reset_index(name="n")
            unique_du4 = du4_count[du4_count["n"] == 1]["DU"]
            mp_du4_unique = (
                mp[mp["DU"].isin(unique_du4)][["DU", "Lat", "Lon", "SITE_NAME", "MARKET", "GNB"]]
                .drop_duplicates(subset=["DU"], keep="first")
                .rename(
                    columns={
                        "DU": "DU4_KEY",
                        "Lat": "lat_du4",
                        "Lon": "lon_du4",
                        "SITE_NAME": "site_du4",
                        "MARKET": "market_du4",
                        "GNB": "gnb_du4",
                    }
                )
            )
            src_du4 = mp_du4_unique.rename(
                columns={
                    "DU4_KEY": "SRC_DU_4",
                    "lat_du4": "src_lat_du4",
                    "lon_du4": "src_lon_du4",
                    "site_du4": "Source_Site_du4",
                    "market_du4": "Source_Market_du4",
                    "gnb_du4": "Source_GNB_du4",
                }
            )
            tgt_du4 = mp_du4_unique.rename(
                columns={
                    "DU4_KEY": "TGT_DU_4",
                    "lat_du4": "tgt_lat_du4",
                    "lon_du4": "tgt_lon_du4",
                    "site_du4": "Target_Site_du4",
                    "market_du4": "Target_Market_du4",
                    "gnb_du4": "Target_GNB_du4",
                }
            )

            merged = (
                relation.merge(src_full, on="SRC_DU_FULL", how="left")
                .merge(tgt_full, on="TGT_DU_FULL", how="left")
                .merge(src_du4, on="SRC_DU_4", how="left")
                .merge(tgt_du4, on="TGT_DU_4", how="left")
            )

            merged["src_lat"] = merged["src_lat_full"].fillna(merged["src_lat_du4"])
            merged["src_lon"] = merged["src_lon_full"].fillna(merged["src_lon_du4"])
            merged["tgt_lat"] = merged["tgt_lat_full"].fillna(merged["tgt_lat_du4"])
            merged["tgt_lon"] = merged["tgt_lon_full"].fillna(merged["tgt_lon_du4"])
            merged["Source_Site"] = merged["Source_Site_full"].fillna(merged["Source_Site_du4"])
            merged["Target_Site"] = merged["Target_Site_full"].fillna(merged["Target_Site_du4"])
            merged["Source_Market"] = merged["Source_Market_full"].fillna(merged["Source_Market_du4"])
            merged["Target_Market"] = merged["Target_Market_full"].fillna(merged["Target_Market_du4"])
            merged["Source_GNB"] = merged["Source_GNB"].fillna(merged["Source_GNB_full"]).fillna(merged["Source_GNB_du4"])
            merged["Target_GNB"] = merged["Target_GNB"].fillna(merged["Target_GNB_full"]).fillna(merged["Target_GNB_du4"])

        # Source fallback by DUNAME
        if "DUNAME" in ho.columns:
            src_name = str(ho["DUNAME"].dropna().iloc[0]) if ho["DUNAME"].dropna().size else None
            if src_name:
                site_rows = mp[mp["SITE_NAME"].astype(str) == src_name] if "SITE_NAME" in mp.columns else pd.DataFrame()
                if not site_rows.empty:
                    merged["src_lat"] = merged["src_lat"].fillna(site_rows["Lat"].mean())
                    merged["src_lon"] = merged["src_lon"].fillna(site_rows["Lon"].mean())
                    merged["Source_Site"] = merged["Source_Site"].fillna(src_name)

        for c in ["src_lat", "src_lon", "tgt_lat", "tgt_lon"]:
            merged[c] = pd.to_numeric(merged[c], errors="coerce")

        mask = merged[["src_lat", "src_lon", "tgt_lat", "tgt_lon"]].notna().all(axis=1)
        merged["Distance_km"] = np.nan
        merged.loc[mask, "Distance_km"] = self._haversine_km(
            merged.loc[mask, "src_lat"].to_numpy(float),
            merged.loc[mask, "src_lon"].to_numpy(float),
            merged.loc[mask, "tgt_lat"].to_numpy(float),
            merged.loc[mask, "tgt_lon"].to_numpy(float),
        )

        merged["Distance_Band"] = pd.cut(
            merged["Distance_km"],
            bins=[-0.001, 1, 3, 5, 10, 999],
            labels=["0-1km", "1-3km", "3-5km", "5-10km", ">10km"],
        )

        # Hide market fields from outputs (kept only for internal compatibility if needed).
        for mc in ["Source_Market", "Target_Market"]:
            if mc in merged.columns:
                merged = merged.drop(columns=[mc])

        # Enforce professional Source -> Target -> KPI layout for every output table.
        merged = merged.rename(
            columns={
                "DU": "Source_DU",
                "SECTOR": "Source_Sector",
                "CARRIER": "Source_Carrier",
                "TGTDU": "Target_DU",
                "TGTSECTOR": "Target_Sector",
                "TGTCARRIER": "Target_Carrier",
            }
        )
        merged["Source_ID"] = self._identifier_series(
            merged,
            ["Source_GNB", "Source_DU"],
            "UNKNOWN_SOURCE",
        )
        merged["Target_ID"] = self._identifier_series(
            merged,
            ["Target_GNB", "Target_DU"],
            "UNKNOWN_TARGET",
        )
        ordered_cols = [
            "Source_ID",
            "Source_Site",
            "Source_GNB",
            "Source_DU",
            "Source_Sector",
            "Source_Carrier",
            "src_lat",
            "src_lon",
            "Target_ID",
            "Target_Site",
            "Target_GNB",
            "Target_DU",
            "Target_Sector",
            "Target_Carrier",
            "tgt_lat",
            "tgt_lon",
            "Distance_km",
            "Distance_Band",
            "Date_Start",
            "Date_End",
            "Observed_Days",
            "Attempts",
            "Success",
            "Failures",
            "Success_Rate",
            "Fail_Rate",
        ]
        ordered_cols = [c for c in ordered_cols if c in merged.columns] + [
            c for c in merged.columns if c not in ordered_cols
        ]
        merged = merged[ordered_cols]

        total_attempts = float(merged["Attempts"].sum())
        total_failures = float(merged["Failures"].sum())
        mapped = merged[merged["Distance_km"].notna()].copy()
        missing_tgt = merged[merged["tgt_lat"].isna() | merged["tgt_lon"].isna()].copy()
        missing_src = merged[merged["src_lat"].isna() | merged["src_lon"].isna()].copy()

        summary = pd.DataFrame(
            [
                ["Total HO Relations", len(merged)],
                ["Mapped Relations", len(mapped)],
                ["Mapped Coverage", len(mapped) / len(merged) if len(merged) else np.nan],
                ["Relations Missing Target Location", len(missing_tgt)],
                ["Relations Missing Source Location", len(missing_src)],
                [
                    "Target Location Coverage",
                    1 - (len(missing_tgt) / len(merged)) if len(merged) else np.nan,
                ],
                ["Total Attempts", total_attempts],
                ["Total Failures", total_failures],
                [
                    "Global Fail Rate",
                    (total_failures / total_attempts) if total_attempts > 0 else np.nan,
                ],
                ["Median Distance (km)", mapped["Distance_km"].median() if len(mapped) else np.nan],
                ["P90 Distance (km)", mapped["Distance_km"].quantile(0.9) if len(mapped) else np.nan],
                ["Max Distance (km)", mapped["Distance_km"].max() if len(mapped) else np.nan],
                [
                    f"Attempts >{self.config.long_handover_km:g}km",
                    mapped.loc[
                        mapped["Distance_km"] > self.config.long_handover_km,
                        "Attempts",
                    ].sum()
                    if len(mapped)
                    else 0,
                ],
            ],
            columns=["KPI", "Value"],
        )

        top_failures = merged.sort_values(["Failures", "Attempts"], ascending=[False, False]).head(
            self.config.top_relations
        )
        long_relations = merged[
            merged["Distance_km"] > self.config.long_handover_km
        ].sort_values(
            ["Failures", "Attempts", "Distance_km"], ascending=[False, False, False]
        )
        distance_bands = (
            mapped.groupby("Distance_Band", observed=False, as_index=False)
            .agg(Relations=("Attempts", "size"), Attempts=("Attempts", "sum"), Failures=("Failures", "sum"))
            .sort_values("Distance_Band")
        )
        distance_bands["Fail_Rate"] = np.where(
            distance_bands["Attempts"] > 0,
            distance_bands["Failures"] / distance_bands["Attempts"],
            np.nan,
        )
        missing_target_locations = missing_tgt.sort_values(
            ["Failures", "Attempts"], ascending=[False, False]
        )

        # Professional "Long HO" table (similar to requested layout screenshot)
        long_ho_table = merged[
            merged["Distance_km"] >= self.config.review_handover_km
        ].copy()
        if "DUNAME" in long_ho_table.columns:
            long_ho_table["DUNAME"] = long_ho_table["DUNAME"].fillna(long_ho_table.get("Source_Site"))
        else:
            long_ho_table["DUNAME"] = long_ho_table.get("Source_Site")
        if "TGTGNB" not in long_ho_table.columns:
            long_ho_table["TGTGNB"] = long_ho_table.get("Target_GNB")
        long_ho_table["HO_Type"] = "Long HO"
        long_ho_table = long_ho_table.rename(
            columns={
                "Source_DU": "DU",
                "Source_Sector": "SECTOR",
                "Source_Carrier": "CARRIER",
                "Target_DU": "TGTDU",
                "Target_Sector": "TGTSECTOR",
                "Target_Carrier": "TGTCARRIER",
                "Target_Site": "Target_Site",
            }
        )
        long_cols = [
            "DUNAME",
            "DU",
            "SECTOR",
            "CARRIER",
            "src_lat",
            "src_lon",
            "TGTGNB",
            "TGTDU",
            "TGTSECTOR",
            "TGTCARRIER",
            "Target_Site",
            "tgt_lat",
            "tgt_lon",
            "Distance_km",
            "Distance_Band",
            "HO_Type",
            "Attempts",
            "Failures",
            "Fail_Rate",
        ]
        long_cols = [c for c in long_cols if c in long_ho_table.columns]
        long_ho_table = long_ho_table[long_cols].sort_values(
            ["Attempts", "Failures", "Distance_km"], ascending=[False, False, False]
        )

        failure_types, failure_detail, source_offenders, target_offenders = (
            self._build_failure_views(merged, fail_cols)
        )

        result = AnalysisResult(
            summary=summary,
            relation_detail=merged,
            top_failures=top_failures,
            long_relations=long_relations,
            distance_bands=distance_bands,
            missing_target_locations=missing_target_locations,
            long_ho_table=long_ho_table,
            failure_types=failure_types,
            failure_detail=failure_detail,
            source_offenders=source_offenders,
            target_offenders=target_offenders,
        )
        self.last_result = result
        return result

    def export_payload(self) -> Dict[str, pd.DataFrame]:
        if not self.last_result:
            raise ValueError("No analysis has been run yet.")
        return {
            "Executive_Summary": self.last_result.summary,
            "Top_Failures": self.last_result.top_failures,
            "Long_Relations_Over10km": self.last_result.long_relations,
            "Long_HO_Table_5kmPlus": self.last_result.long_ho_table,
            "Distance_Bands": self.last_result.distance_bands,
            "Missing_Target_Locations": self.last_result.missing_target_locations,
            "Failure_Types": self.last_result.failure_types,
            "Failure_Detail": self.last_result.failure_detail,
            "Source_Offenders": self.last_result.source_offenders,
            "Target_Offenders": self.last_result.target_offenders,
            "Source_Target_Detail": self.last_result.relation_detail,
        }
