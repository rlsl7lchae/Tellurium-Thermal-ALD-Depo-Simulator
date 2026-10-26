"""Preprocess the ALD workbook without modifying the raw measurements."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Iterable

import numpy as np
import pandas as pd

from recipe_parser_v2 import (
    ROUTE_GETE_GESE_THEN_TE,
    ROUTE_GETE_ONLY,
    ROUTE_GETE_THEN_TE,
    ROUTE_TE_2STEP,
    ROUTE_TE_4STEP,
    ROUTE_TE_COREACTANT_4STEP,
    ROUTE_TE_OXIDE,
    parse_recipe,
)


DEFAULT_SHEET = "Te"
RECIPE_COL = "(Experiment Set)\nRecipe Name"

REQUIRED_COLUMNS = [
    RECIPE_COL,
    "Depo. Temp. (℃)",
    "Throttle",
    "sub.",
    "Pulse Scheme",
    "Working P",
    "Reactant",
]

RESULT_COLUMNS = [
    "GPC (Å/cy)",
    "GPC (ng/cm2/cy)",
    "thickness (nm)",
    "Layer density\n(ug/cm^2)",
    "Ge (at%)",
    "Se (at%)",
    "Te (at%)",
]

NUMERIC_RAW_COLUMNS = [
    "Depo. Temp. (℃)",
    "Stage Temp",
    "Toplid Temp",
    "Wall Temp",
    "cycle#",
    *RESULT_COLUMNS,
]


def _validate_columns(df: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError("필수 열이 없습니다: " + ", ".join(missing))


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def parse_working_pressure(value: object) -> tuple[float | None, float | None, str]:
    if pd.isna(value):
        return None, None, "Working P 결측"
    text = str(value).strip()
    pressure_match = re.search(r"(\d+(?:\.\d+)?)\s*torr", text, re.IGNORECASE)
    flow_match = re.search(r"Ar\s*:\s*(\d+(?:\.\d+)?)\s*sccm", text, re.IGNORECASE)
    pressure = float(pressure_match.group(1)) if pressure_match else None
    flow = float(flow_match.group(1)) if flow_match else None
    notes: list[str] = []
    if pressure is None:
        notes.append("압력 파싱 실패")
    if flow is None:
        notes.append("Ar 유량 파싱 실패")
    return pressure, flow, "; ".join(notes)


def normalize_throttle(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip().lower()
    return {"clsoed": "closed", "fully open": "open"}.get(text, text)


def normalize_substrate(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower().startswith("sio2"):
        return "SiO2"
    return text


def load_raw_workbook(path: str | Path, sheet_name: str = DEFAULT_SHEET) -> pd.DataFrame:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"원본 Excel 파일이 없습니다: {source}")
    raw = pd.read_excel(source, sheet_name=sheet_name, header=0)
    _validate_columns(raw)
    meaningful = raw[RECIPE_COL].notna() & raw[RECIPE_COL].astype(str).str.strip().ne("")
    result = raw.loc[meaningful].copy()
    result.insert(0, "source_excel_row", result.index + 2)
    return result.reset_index(drop=True)


def _coalesce_cycle_fields(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    total = out["cycle_total_excel"]
    route = out["deposition_route"]

    direct_routes = {
        ROUTE_TE_2STEP,
        ROUTE_TE_4STEP,
        ROUTE_TE_COREACTANT_4STEP,
        ROUTE_TE_OXIDE,
    }
    direct_mask = route.isin(direct_routes) & out["te_cycle"].isna() & total.notna()
    out.loc[direct_mask, "te_cycle"] = total[direct_mask]

    gete_only_mask = route.eq(ROUTE_GETE_ONLY) & out["gete_cycle"].isna() & total.notna()
    out.loc[gete_only_mask, "gete_cycle"] = total[gete_only_mask]

    sequential = route.isin({ROUTE_GETE_THEN_TE, ROUTE_GETE_GESE_THEN_TE})
    derive_gete = sequential & out["gete_cycle"].isna() & out["te_cycle"].notna() & total.notna()
    derived_gete = total - out["te_cycle"]
    out.loc[derive_gete & derived_gete.ge(0), "gete_cycle"] = derived_gete[derive_gete & derived_gete.ge(0)]

    derive_te = sequential & out["te_cycle"].isna() & out["gete_cycle"].notna() & total.notna()
    known_other = out["gete_cycle"].fillna(0) + out["gese_doping_cycle"].fillna(0)
    derived_te = total - known_other
    out.loc[derive_te & derived_te.ge(0), "te_cycle"] = derived_te[derive_te & derived_te.ge(0)]

    out["gete_te_cycle_ratio"] = out["gete_cycle"] / out["te_cycle"].replace(0, np.nan)
    parsed_components = (
        out["gete_cycle"].fillna(0)
        + out["gese_doping_cycle"].fillna(0)
        + out["te_cycle"].fillna(0)
        + out["post_gese_cap_cycle"].fillna(0)
        + out["cte_cycle"].fillna(0)
        + out["al2o3_cap_cycle"].fillna(0)
    )
    out["cycle_total_parsed"] = parsed_components.where(parsed_components.gt(0))
    out["cycle_total_difference"] = out["cycle_total_excel"] - out["cycle_total_parsed"]
    return out


def preprocess_dataframe(raw: pd.DataFrame) -> pd.DataFrame:
    """Return a processed copy; never mutate the source dataframe."""
    _validate_columns(raw)
    out = raw.copy().reset_index(drop=True)
    if "source_excel_row" not in out:
        out.insert(0, "source_excel_row", np.arange(2, len(out) + 2))

    for column in NUMERIC_RAW_COLUMNS:
        if column not in out:
            out[column] = np.nan
        out[column] = _numeric(out[column])

    parsed_rows = [
        parse_recipe(row.get(RECIPE_COL), row.get("Pulse Scheme"), row.get("Reactant")).to_dict()
        for _, row in out.iterrows()
    ]
    parsed = pd.DataFrame(parsed_rows, index=out.index)
    duplicate_names = [column for column in parsed.columns if column in out.columns]
    if duplicate_names:
        parsed = parsed.drop(columns=duplicate_names)
    out = pd.concat([out, parsed], axis=1)

    pressure_rows = out["Working P"].apply(parse_working_pressure)
    out["pressure_torr"] = [item[0] for item in pressure_rows]
    out["ar_flow_sccm"] = [item[1] for item in pressure_rows]
    out["working_p_note"] = [item[2] for item in pressure_rows]
    out["throttle_normalized"] = out["Throttle"].apply(normalize_throttle)
    out["substrate_normalized"] = out["sub."].apply(normalize_substrate)
    out["cycle_total_excel"] = out["cycle#"]
    for column in (
        "gete_cycle",
        "te_cycle",
        "gese_doping_cycle",
        "post_gese_cap_cycle",
        "cte_cycle",
        "al2o3_cap_cycle",
    ):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = _coalesce_cycle_fields(out)

    out["gpc_missing"] = out["GPC (Å/cy)"].isna()
    out["gpc_nonpositive"] = out["GPC (Å/cy)"].notna() & out["GPC (Å/cy)"].le(0)
    out["gpc_recomputed"] = (
        out["thickness (nm)"] * 10 / out["cycle_total_excel"].replace(0, np.nan)
    )
    out["gpc_recompute_error"] = out["GPC (Å/cy)"] - out["gpc_recomputed"]
    out["gpc_formula_consistent"] = (
        out["gpc_recompute_error"].abs().le(1e-8)
        & out["GPC (Å/cy)"].notna()
        & out["gpc_recomputed"].notna()
    )

    target_present = pd.DataFrame(
        {column: out[column].notna() for column in RESULT_COLUMNS if column in out}
    )
    out["result_missing"] = ~target_present.any(axis=1)
    out["preprocess_note"] = ""
    out.loc[out["parse_status"].ne("ok"), "preprocess_note"] = out["parse_note"]
    out.loc[out["working_p_note"].ne(""), "preprocess_note"] = (
        out.loc[out["working_p_note"].ne(""), "preprocess_note"].str.strip("; ")
        + "; "
        + out.loc[out["working_p_note"].ne(""), "working_p_note"]
    ).str.strip("; ")
    return out


def preprocess_workbook(path: str | Path, sheet_name: str = DEFAULT_SHEET) -> pd.DataFrame:
    return preprocess_dataframe(load_raw_workbook(path, sheet_name))


def summarize_preprocessing(df: pd.DataFrame) -> str:
    route_counts = df["deposition_route"].value_counts(dropna=False).to_dict()
    lines = [
        f"유효 실험행: {len(df)}",
        f"GPC 측정값 보유: {int(df['GPC (Å/cy)'].notna().sum())}",
        f"GPC 양수: {int(df['GPC (Å/cy)'].gt(0).sum())}",
        f"Recipe 파싱 경고/실패: {int(df['parse_status'].ne('ok').sum())}",
        "공정 경로별 건수:",
    ]
    lines.extend(f"  - {route}: {count}" for route, count in route_counts.items())
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ALD 원본 Excel을 v2 분석용 CSV로 전처리합니다.")
    parser.add_argument("input", type=Path, help="원본 XRF Excel 경로")
    parser.add_argument("--sheet", default=DEFAULT_SHEET, help="시트명 (기본값: Te)")
    parser.add_argument("--output", type=Path, default=Path("te_preprocessed_v2.csv"))
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    processed = preprocess_workbook(args.input, args.sheet)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    processed.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(summarize_preprocessing(processed))
    print(f"저장: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
