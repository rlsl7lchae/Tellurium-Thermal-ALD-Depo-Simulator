# -*- coding: utf-8 -*-
"""
Te_ALD_Simulator.html 용 data.json 재생성 파이프라인.

v1(build_pipeline.py)을 분실해서, v2 프로젝트의 검증된 파서(recipe_parser_v2 /
preprocess_v2)를 재사용해 새로 만들었다. 방법론은 기존 대시보드 JSON을 역분석해서
최대한 동일하게 맞췄다 (특히 GPC = thickness*10/te_cycle 인 것을 확인함 — 이 기준으로
회귀 표본수가 기존 159건과 거의 일치하는 160건이 나옴).

사용법:
    python build_dashboard_data.py XRF_Te.xlsx data.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from preprocess_v2 import load_raw_workbook, preprocess_dataframe

RNG = np.random.default_rng(0)
N_BOOT = 1000

# ---------------------------------------------------------------- 알려진 오타 보정
# 2022-11-24로 찍힌 행 1건은 장비가 2025년 것부터 있어서 오타로 확인됨 (사용자 확인, 2025-11-24로 정정)
DATE_FIX = {"2022-11-24": "2025-11-24"}

# 안정화기 (사용자가 직접 판단한 구간)
STABLE_START, STABLE_END = "2025-10-01", "2026-01-14"

SEEDED_ROUTES = {"GETE_THEN_TE", "GETE_GESE_THEN_TE"}
SE_DOPED_ROUTES = {"GETE_GESE_THEN_TE"}   # GeTe seed 위에 GeSe 도핑 후 Te 성장
SYSTEM_LABEL = {
    "GETE_ONLY": "GeTe only",
    "GETE_THEN_TE": "GeTe/Te",
    "GETE_GESE_THEN_TE": "GeTe+GeSe/Te",
    "GESE_ONLY": "GeSe only",
    "TE_2STEP": "Te only",
    "TE_4STEP": "Te only",
    "TE_COREACTANT_4STEP": "Te only",
    "TE_OXIDE": "TeO2",
    "OTHER_COMPLEX_ROUTE": "Other",
    "PARSE_UNCERTAIN": "Other",
}


def norm_reactant(name: str) -> str:
    if name in ("Isopropylamine", "Methanol", "DIW"):
        return name
    return "None(Ar)"  # Ar-only, blank, or malformed co-reactant text


def temp_bin(t):
    if t is None or (isinstance(t, float) and np.isnan(t)):
        return None
    if t < 100:
        return "T<100"
    if t < 140:
        return "T100-140"
    if t < 190:
        return "T140-190"
    if t < 230:
        return "T190-230"
    return "T>=230"


def parse_line_t(etc: str):
    if not etc:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*도", etc)
    if m and ("Line" in etc or "line" in etc or "히팅" in etc):
        return float(m.group(1))
    return None


def parse_needle(etc: str):
    if not etc:
        return None
    m = re.search(r"[Nn]eedle\s*[Vv]alve\s*\(?\s*(\d+(?:\.\d+)?)\s*(?:바퀴|만큼)", etc)
    if m:
        return float(m.group(1))
    return None


def parse_n_coupon(etc: str):
    if not etc:
        return None
    m = re.search(r"시편\s*(\d+)\s*개", etc)
    return int(m.group(1)) if m else None


def parse_stage(sub_raw: str):
    if not sub_raw:
        return None
    for tag in ("위", "가운데", "아래"):
        if sub_raw.endswith("_" + tag):
            return tag
    return None


def _frac_to_pct(value):
    """엑셀 조성 칸은 분율(0.29 = 29 at%)로 저장돼 있어 at%로 바꾼다."""
    if value is None or pd.isna(value):
        return None
    return round(float(value) * 100.0, 2)


def build_rows(df: pd.DataFrame, raw: pd.DataFrame) -> list[dict]:
    rows = []
    for i, r in df.iterrows():
        date = pd.Timestamp(r["Date"]).strftime("%Y-%m-%d") if pd.notna(r["Date"]) else None
        date = DATE_FIX.get(date, date)

        te_cy = r["te_cycle"]
        thick = r["thickness (nm)"]
        gpc = None
        if pd.notna(thick) and pd.notna(te_cy) and te_cy not in (0, None):
            g = thick * 10.0 / te_cy
            if g > 0:
                gpc = round(float(g), 4)

        etc = str(raw.loc[i, "etc."]) if pd.notna(raw.loc[i, "etc."]) else ""
        sub_raw = str(raw.loc[i, "sub."]) if pd.notna(raw.loc[i, "sub."]) else ""

        row = {
            "date": date,
            "recipe": (str(r["recipe_name"])[:60] if pd.notna(r["recipe_name"]) else ""),
            "system": SYSTEM_LABEL.get(r["deposition_route"], "Other"),
            "temp": float(r["Depo. Temp. (℃)"]) if pd.notna(r["Depo. Temp. (℃)"]) else None,
            "sub": r["substrate_normalized"] or None,
            "reactant": norm_reactant(r["co_reactant_name"]),
            "press": float(r["pressure_torr"]) if pd.notna(r["pressure_torr"]) else None,
            "ar": float(r["ar_flow_sccm"]) if pd.notna(r["ar_flow_sccm"]) else None,
            "te_cy": float(te_cy) if pd.notna(te_cy) else None,
            "gete_cy": float(r["gete_cycle"]) if pd.notna(r["gete_cycle"]) else None,
            "gese_cy": float(r["gese_doping_cycle"]) if pd.notna(r["gese_doping_cycle"]) else None,
            "dens": float(r["Layer density\n(ug/cm^2)"]) if pd.notna(r["Layer density\n(ug/cm^2)"]) else None,
            "thick": float(thick) if pd.notna(thick) else None,
            "te_at": float(r["Te (at%)"]) if pd.notna(r["Te (at%)"]) else None,
            "gpc": gpc,
            "nodep": bool(pd.isna(thick) or thick == 0),
            "seeded": r["deposition_route"] in SEEDED_ROUTES,
            "se_doped": r["deposition_route"] in SE_DOPED_ROUTES,
            "se_at": _frac_to_pct(r["Se (at%)"]),
            "ge_at": _frac_to_pct(r["Ge (at%)"]),
            "cap_cy": float(r["post_gese_cap_cycle"]) if pd.notna(r["post_gese_cap_cycle"]) else None,
            "stable": bool(date and STABLE_START <= date <= STABLE_END),
            "line_t": parse_line_t(etc),
            "needle": parse_needle(etc),
            "stage": parse_stage(sub_raw),
            "n_coupon": parse_n_coupon(etc),
            "pos_memo": bool(re.search(r"위쪽|가운데|아래", etc)),
            "issue": etc if etc.strip() else None,
        }
        rows.append(row)
    return rows


# ---------------------------------------------------------------- 회귀
def design_matrix(rows: list[dict]):
    cats_reactant = ["Methanol", "DIW", "None(Ar)"]  # ref = Isopropylamine
    cats_sub = ["Sapphire", "Ni"]                     # ref = SiO2 (TiN 별도 제외)
    cats_tbin = ["T100-140", "T140-190", "T190-230", "T>=230"]  # ref = T<100

    TE_SYSTEMS = {"Te only", "GeTe/Te", "GeTe+GeSe/Te"}  # 실제 Te 층이 증착되는 경로만 (GeSe only/TeO2/Other 제외)
    # te_cy가 아주 작은 점(<20)은 핵생성 지연(n0) 구간이라 GPC=thick/cycle이 안정적이지 않음
    # (별도로 fits/n0 선형적합에서 다룸) -> 정상상태 로그선형회귀에서는 제외
    fit_rows = [r for r in rows if r["gpc"] and r["sub"] != "TiN" and r["sub"] is not None
                and r["reactant"] is not None and temp_bin(r["temp"]) is not None
                and r["system"] in TE_SYSTEMS and r["te_cy"] and r["te_cy"] >= 20]

    # seeded  : GeTe seed 위 성장 (GeTe/Te, GeTe+GeSe/Te 둘 다 1)
    # se_doped: 그중 GeSe 도핑까지 한 경우만 1 → seed 효과에 "추가로" 곱해지는 Se 도핑 효과
    names = ["const"] + [f"reactant={c}" for c in cats_reactant] + \
            [f"sub={c}" for c in cats_sub] + [f"tbin={c}" for c in cats_tbin] + ["seeded", "se_doped"]

    X = np.zeros((len(fit_rows), len(names)))
    y = np.zeros(len(fit_rows))
    for i, r in enumerate(fit_rows):
        X[i, 0] = 1.0
        if r["reactant"] in cats_reactant:
            X[i, 1 + cats_reactant.index(r["reactant"])] = 1.0
        if r["sub"] in cats_sub:
            X[i, 1 + len(cats_reactant) + cats_sub.index(r["sub"])] = 1.0
        tb = temp_bin(r["temp"])
        if tb in cats_tbin:
            X[i, 1 + len(cats_reactant) + len(cats_sub) + cats_tbin.index(tb)] = 1.0
        X[i, -2] = 1.0 if r["seeded"] else 0.0
        X[i, -1] = 1.0 if r.get("se_doped") else 0.0
        y[i] = np.log(r["gpc"])
    return X, y, names, fit_rows


def fit_ols(X, y, names):
    """rank-deficient 대비: 컬럼에 분산이 없으면 계수 0 / CI [1,1] 로 고정."""
    keep = [j for j in range(X.shape[1]) if j == 0 or X[:, j].std() > 1e-9]
    beta_full = np.zeros(X.shape[1])
    if len(y) >= len(keep):
        beta, *_ = np.linalg.lstsq(X[:, keep], y, rcond=None)
        for j, b in zip(keep, beta):
            beta_full[j] = b
    resid = y - X[:, keep] @ beta_full[keep] if len(y) else np.array([0.0])
    sigma = float(np.std(resid, ddof=max(1, len(keep)))) if len(y) > len(keep) else 0.0
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2)) if len(y) else 0.0
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # bootstrap CI (exp화된 배율로)
    boot = np.zeros((N_BOOT, X.shape[1]))
    n = len(y)
    for b in range(N_BOOT if n >= len(keep) + 2 else 0):
        idx = RNG.integers(0, n, n)
        Xb, yb = X[idx][:, keep], y[idx]
        if np.linalg.matrix_rank(Xb) < len(keep):
            boot[b] = beta_full
            continue
        beta_b, *_ = np.linalg.lstsq(Xb, yb, rcond=None)
        bb = np.zeros(X.shape[1])
        for j, v in zip(keep, beta_b):
            bb[j] = v
        boot[b] = bb

    coef, ci = {}, {}
    for j, name in enumerate(names):
        if name == "const":
            coef[name] = round(float(beta_full[j]), 4)
            lo, hi = np.percentile(np.exp(boot[:, j]), [2.5, 97.5]) if n >= len(keep) + 2 else (np.exp(beta_full[j]),) * 2
            ci[name] = [round(float(lo), 3), round(float(hi), 3)]
            continue
        coef[name] = round(float(beta_full[j]), 4)
        if j not in keep:
            ci[name] = [1.0, 1.0]
        else:
            lo, hi = np.percentile(np.exp(boot[:, j]), [2.5, 97.5]) if n >= len(keep) + 2 else (np.exp(beta_full[j]),) * 2
            ci[name] = [round(float(lo), 3), round(float(hi), 3)]
    return coef, ci, sigma, r2, len(y)


def seed_state(r: dict) -> str:
    """시뮬레이터의 하지층 선택지와 같은 3분류: bare / seed(GeTe) / se(GeTe + Se 도핑)."""
    if r.get("se_doped"):
        return "se"
    return "seed" if r["seeded"] else "bare"


def linfit_intercept(cycles, thick):
    """thick = gpc*(cycle - n0) 형태의 직선 적합 -> (gpc, n0)."""
    cycles = np.asarray(cycles, dtype=float)
    thick = np.asarray(thick, dtype=float)
    if len(cycles) < 2 or cycles.std() == 0:
        return (float(thick.mean() / cycles.mean()) if len(cycles) and cycles.mean() else 0.0, 0.0)
    slope, intercept = np.polyfit(cycles, thick, 1)
    if slope <= 0:
        return (0.0, 0.0)
    n0 = max(0.0, -intercept / slope)
    return float(slope), float(n0)


def build_model(rows: list[dict], subset_rows=None):
    use = subset_rows if subset_rows is not None else rows
    X, y, names, fit_rows = design_matrix(use)
    coef, ci, sigma, r2, n_fit = fit_ols(X, y, names)

    # n0 (bare = seeded 아닌 것) / fits (전체, reactant별 두께~cycle 선형적합)
    TE_SYSTEMS = {"Te only", "GeTe/Te", "GeTe+GeSe/Te"}
    n0, fits = {}, {}
    for rx in ["Isopropylamine", "Methanol", "DIW"]:
        bare = [r for r in use if r["reactant"] == rx and not r["seeded"] and r["system"] in TE_SYSTEMS
                and r["te_cy"] and r["thick"] is not None]
        if len(bare) >= 2:
            _, n0_val = linfit_intercept([r["te_cy"] for r in bare], [r["thick"] for r in bare])
            n0[rx] = round(n0_val, 1)
        else:
            n0[rx] = 0.0

        allrx = [r for r in use if r["reactant"] == rx and r["system"] in TE_SYSTEMS
                 and r["te_cy"] and r["thick"] is not None]
        if len(allrx) >= 2:
            slope, n0f = linfit_intercept([r["te_cy"] for r in allrx], [r["thick"] for r in allrx])
        else:
            slope, n0f = (allrx[0]["gpc"] or 0.0, 0.0) if allrx else (0.0, 0.0)
        fits[rx] = {"gpc": round(slope * 10.0, 4), "n0": round(n0f, 1), "n": len(allrx)}

    # succ (기판별 무증착 아닌 비율)
    succ = {}
    for sub in ["SiO2", "Sapphire", "TiN", "Ni"]:
        sr = [r for r in use if r["sub"] == sub]
        succ[sub] = round(1 - sum(r["nodep"] for r in sr) / len(sr), 2) if sr else None
    succ = {k: v for k, v in succ.items() if v is not None}

    # cv_map: 같은 (date,recipe) 그룹 내 두께 CV%를 seed 상태|reactant 로 집계
    from collections import defaultdict
    groups = defaultdict(list)
    for r in use:
        if r["thick"] and r["date"] and r["recipe"]:
            groups[(r["date"], r["recipe"])].append(r)
    cv_by_cat = defaultdict(list)
    for g in groups.values():
        if len(g) < 2:
            continue
        vals = [r["thick"] for r in g]
        cv = float(np.std(vals, ddof=1) / np.mean(vals) * 100) if np.mean(vals) else None
        if cv is None:
            continue
        rx = g[0]["reactant"]
        cat = seed_state(g[0]) + "|" + rx
        cv_by_cat[cat].append(cv)
    cv_map = {
        k: {"mean": round(float(np.mean(v)), 1), "med": round(float(np.median(v)), 1), "n": len(v)}
        for k, v in cv_by_cat.items()
    }

    # ALD window: SiO2/Sapphire x Isopropylamine, 온도군 근접치 사용
    def window(sub, targets):
        # Methanol만 150~250도 온도 스윕 데이터가 있어 ALD 자기제한성 창 분석에 사용됨
        cand = [r for r in use if r["sub"] == sub and r["reactant"] == "Methanol"
                and r["gpc"] and r["temp"] and r["te_cy"] and r["te_cy"] >= 20]
        picked = []
        for t in targets:
            near = min(cand, key=lambda r: abs(r["temp"] - t), default=None)
            if near is not None and abs(near["temp"] - t) <= 15:
                picked.append(near)
        if len(picked) < 2:
            return None
        gpcs = [p["gpc"] for p in picked]
        spread = round((max(gpcs) - min(gpcs)) / np.mean(gpcs) * 100, 1) if np.mean(gpcs) else None
        return {"temps": [p["temp"] for p in picked], "gpc": [round(g, 4) for g in gpcs], "spread": spread}

    ald = {
        "winA": window("SiO2", [150, 175, 200]),
        "winA_sap": window("Sapphire", [150, 175, 200]),
        "winB": window("SiO2", [150, 200, 250]),
        "winB_sap": window("Sapphire", [150, 200, 250]),
    }

    tmid = {"T<100": 90, "T100-140": 120, "T140-190": 165, "T190-230": 210, "T>=230": 250}

    return {
        "coef": coef, "ci": ci, "ald": ald, "sigma": round(sigma, 3), "r2": round(r2, 3),
        "n_fit": n_fit, "n0": n0, "succ": succ, "cv_map": cv_map, "fits": fits, "tmid": tmid,
    }


# ---------------------------------------------------------------- 검증 (학습/테스트 분리)
TEST_FRACTION = 0.2   # 가장 최근 날짜 순으로 회귀 표본의 약 20%를 테스트용으로 떼어둔다
N_FOLDS = 5


def _ols_fit_predict(X_tr, y_tr, X_te):
    """학습 데이터로 적합하고 테스트 데이터를 예측. 학습에서 분산 0인 열은 계수 0."""
    keep = [j for j in range(X_tr.shape[1]) if j == 0 or X_tr[:, j].std() > 1e-9]
    beta, *_ = np.linalg.lstsq(X_tr[:, keep], y_tr, rcond=None)
    full = np.zeros(X_tr.shape[1])
    for j, b in zip(keep, beta):
        full[j] = b
    unseen = [j for j in range(1, X_tr.shape[1]) if j not in keep and X_te[:, j].any()]
    return X_tr @ full, X_te @ full, unseen


def _r2(y, p):
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return 1 - float(np.sum((y - p) ** 2)) / ss_tot if ss_tot > 0 else 0.0


def build_validation(rows: list[dict]) -> dict | None:
    """시간순 홀드아웃(과거 → 학습, 최근 → 테스트) + k-fold 교차검증.

    회귀 표본(design_matrix 기준)만 사용한다. 같은 날짜는 같은 쪽에 묶어서,
    같은 날 같은 조건으로 찍은 반복 측정이 학습/테스트에 나뉘어 들어가지 않게 한다.
    """
    X, y, names, fit_rows = design_matrix(rows)
    n = len(y)
    if n < 30:
        return None

    dates = np.array([r["date"] or "" for r in fit_rows])
    order = np.argsort(dates, kind="stable")
    n_test_target = max(5, int(round(n * TEST_FRACTION)))
    cutoff = dates[order][n - n_test_target]          # 이 날짜부터 테스트
    te = dates >= cutoff
    tr = ~te
    if tr.sum() < len(names) + 2 or te.sum() < 5:
        return None

    p_tr, p_te, unseen = _ols_fit_predict(X[tr], y[tr], X[te])
    resid_tr = y[tr] - p_tr
    resid_te = y[te] - p_te
    k = len([j for j in range(X.shape[1]) if j == 0 or X[tr][:, j].std() > 1e-9])
    sigma_tr = float(np.std(resid_tr, ddof=min(k, int(tr.sum()) - 1)))
    band = np.exp(sigma_tr)

    # k-fold 교차검증 (무작위, 재현 가능하도록 seed 고정)
    rng = np.random.default_rng(0)
    idx = rng.permutation(n)
    folds = np.array_split(idx, N_FOLDS)
    cv_r2, cv_err = [], []
    for f in folds:
        m = np.zeros(n, dtype=bool)
        m[f] = True
        _, p, _ = _ols_fit_predict(X[~m], y[~m], X[m])
        cv_r2.append(round(_r2(y[m], p), 3))
        cv_err.append(float(np.median(np.abs(y[m] - p))))

    # 테스트 구간을 계열별로 쪼갠 오차 (Se 도핑 항이 어디에 도움이 되고 어디서 틀리는지)
    systems = np.array([r["system"] for r in fit_rows])
    by_system = []
    for sysname in ("Te only", "GeTe/Te", "GeTe+GeSe/Te"):
        m = te & (systems == sysname)
        if m.sum() == 0:
            continue
        r_ = y[m] - p_te[m[te]]
        by_system.append({
            "system": sysname, "n": int(m.sum()),
            "bias_ratio": round(float(np.exp(np.mean(r_))), 3),
            "med_ratio": round(float(np.exp(np.median(np.abs(r_)))), 3),
        })

    # 비교용: Se 도핑 항을 뺀 예전 모델(seed 있음/없음만)로 같은 분리를 했을 때
    no_se = [j for j, nm in enumerate(names) if nm != "se_doped"]
    _, p_te0, _ = _ols_fit_predict(X[tr][:, no_se], y[tr], X[te][:, no_se])
    r0 = y[te] - p_te0
    by_system_no_se = {}
    for sysname in ("Te only", "GeTe/Te", "GeTe+GeSe/Te"):
        m = systems[te] == sysname
        if m.any():
            by_system_no_se[sysname] = {
                "bias_ratio": round(float(np.exp(np.mean(r0[m]))), 3),
                "med_ratio": round(float(np.exp(np.median(np.abs(r0[m])))), 3),
            }
    without_se = {
        "test_r2": round(_r2(y[te], p_te0), 3),
        "test_med_ratio": round(float(np.exp(np.median(np.abs(r0)))), 3),
        "test_bias_ratio": round(float(np.exp(np.mean(r0))), 3),
        "by_system": by_system_no_se,
    }

    def span(mask):
        ds = sorted(d for d in dates[mask].tolist() if d)
        return [ds[0], ds[-1]] if ds else [None, None]

    def pts(mask, pred):
        return [[round(float(np.exp(a)), 4), round(float(np.exp(b)), 4)]
                for a, b in zip(y[mask], pred)]

    return {
        "method": "time_holdout",
        "cutoff": str(cutoff),
        "train_span": span(tr),
        "test_span": span(te),
        "n_train": int(tr.sum()),
        "n_test": int(te.sum()),
        "train_r2": round(_r2(y[tr], p_tr), 3),
        "test_r2": round(_r2(y[te], p_te), 3),
        "train_sigma": round(sigma_tr, 3),
        "test_rmse_log": round(float(np.sqrt(np.mean(resid_te ** 2))), 3),
        # 예측값 대비 실제값이 몇 배 어긋났는지 (중앙값). 1.20 = 약 20% 오차
        "test_med_ratio": round(float(np.exp(np.median(np.abs(resid_te)))), 3),
        # 평균적으로 실제/예측 배율. 0.83 = 실제가 예측보다 17% 낮음 (과대예측)
        "test_bias_ratio": round(float(np.exp(np.mean(resid_te))), 3),
        # 학습 잔차로 만든 ×band 범위 안에 테스트 실측이 들어온 비율
        "test_in_band": round(float(np.mean(np.abs(resid_te) <= sigma_tr)), 3),
        "band": round(float(band), 2),
        "test_y_sd": round(float(np.std(y[te])), 3),
        "train_y_sd": round(float(np.std(y[tr])), 3),
        "unseen_terms": [names[j] for j in unseen],
        "cv_folds": N_FOLDS,
        "cv_r2": cv_r2,
        "cv_r2_mean": round(float(np.mean(cv_r2)), 3),
        "cv_med_ratio": round(float(np.exp(np.mean(cv_err))), 3),
        "train_pts": pts(tr, p_tr),
        "test_pts": pts(te, p_te),
        "test_se": [bool(r["se_doped"]) for r, t in zip(fit_rows, te) if t],
        "by_system": by_system,
        "without_se": without_se,
    }


# ---------------------------------------------------------------- Se 도핑 분석
def _spearman(xs, ys):
    """순위 상관(스피어만). 표본이 적거나 한쪽이 상수면 None."""
    if len(xs) < 5:
        return None
    rx = pd.Series(xs).rank()
    ry = pd.Series(ys).rank()
    if rx.std() == 0 or ry.std() == 0:
        return None
    return round(float(np.corrcoef(rx, ry)[0, 1]), 3)


def _med(vals):
    vals = [v for v in vals if v is not None]
    return round(float(np.median(vals)), 3) if vals else None


def build_se_analysis(rows: list[dict], model: dict) -> dict | None:
    """GeTe/Te 와 GeTe + Se 도핑 / Te 를 비교하고, 도핑 cycle에 따른 Se 함량을 정리한다.

    기간 토글과 무관하게 전체 데이터 기준 (Se 도핑 실험은 2026-03 이후라 안정화기에는 없음).
    """
    from collections import defaultdict

    groups = {
        "GeTe/Te": [r for r in rows if r["seeded"] and not r["se_doped"]],
        "GeTe+GeSe/Te": [r for r in rows if r["se_doped"]],
    }
    if not groups["GeTe+GeSe/Te"]:
        return None

    def cv_median(rs):
        by_run = defaultdict(list)
        for r in rs:
            if r["thick"] and r["date"] and r["recipe"]:
                by_run[(r["date"], r["recipe"])].append(r["thick"])
        cvs = [float(np.std(v, ddof=1) / np.mean(v) * 100) for v in by_run.values() if len(v) >= 2]
        return (round(float(np.median(cvs)), 1) if cvs else None), len(cvs)

    compare = {}
    for label, rs in groups.items():
        # Te 위에 GeSe 캡층을 올린 시편은 XRF Se가 캡층에서 나오므로 도핑 비교에서 뺀다
        deposited = [r for r in rs if not r["nodep"] and r["cap_cy"] is None]
        se_vals = [r["se_at"] for r in deposited if r["se_at"] is not None]
        cv_med, cv_n = cv_median(rs)
        compare[label] = {
            "n": len(rs),
            "nodep_rate": round(sum(r["nodep"] for r in rs) / len(rs), 3) if rs else None,
            "gpc_med": _med([r["gpc"] for r in rs]),
            "se_med": _med(se_vals),                              # 증착된 시편 전체 기준
            "se_med_detected": _med([v for v in se_vals if v > 0]),  # Se가 검출된(>0) 시편 기준
            "se_n": len(se_vals),
            "se_detected_n": sum(1 for v in se_vals if v > 0),
            "cv_med": cv_med,
            "cv_runs": cv_n,
        }

    pts = []
    for r in groups["GeTe+GeSe/Te"]:
        if r["nodep"] or r["se_at"] is None or r["gese_cy"] is None:
            continue
        gete = r["gete_cy"] or 0.0
        pts.append({
            "date": r["date"],
            "dop_cy": r["gese_cy"],
            "gete_cy": r["gete_cy"],
            "te_cy": r["te_cy"],
            # 하지층(GeTe+GeSe) 안에서 GeSe가 차지하는 cycle 비율
            "dop_frac": round(r["gese_cy"] / (gete + r["gese_cy"]), 3) if (gete + r["gese_cy"]) else None,
            "se": r["se_at"],
            "thick": r["thick"],
            "cap": r["cap_cy"] is not None,
        })

    by_cy = defaultdict(list)
    for p in pts:
        if not p["cap"]:
            by_cy[p["dop_cy"]].append(p["se"])
    by_cycle = [
        {"dop_cy": cy, "n": len(v), "se_med": round(float(np.median(v)), 1),
         "se_min": round(float(min(v)), 1), "se_max": round(float(max(v)), 1)}
        for cy, v in sorted(by_cy.items())
    ]

    no_cap = [p for p in pts if not p["cap"]]
    return {
        "compare": compare,
        "points": pts,
        "by_cycle": by_cycle,
        "rho_cycle": _spearman([p["dop_cy"] for p in no_cap], [p["se"] for p in no_cap]),
        "rho_frac": _spearman([p["dop_frac"] for p in no_cap if p["dop_frac"] is not None],
                              [p["se"] for p in no_cap if p["dop_frac"] is not None]),
        "n_rho": len(no_cap),
        "coef": model["coef"].get("se_doped"),
        "ci": model["ci"].get("se_doped"),
        "seed_coef": model["coef"].get("seeded"),
        "n_fit_se": int(sum(1 for r in design_matrix(rows)[3] if r["se_doped"])),
    }


def build_hidden(rows: list[dict]) -> dict:
    def groupstat(key, cast=str):
        buckets = defaultdict(list)
        for r in rows:
            v = r.get(key)
            if v is None or r["thick"] is None or r["nodep"]:
                continue
            buckets[cast(v)].append(r["thick"])
        out = {}
        for k, vals in buckets.items():
            if len(vals) < 2:
                continue
            out[k] = {"n": len(vals), "mean": round(float(np.mean(vals)), 2), "sd": round(float(np.std(vals, ddof=1)), 2)}
        return out

    from collections import defaultdict
    hidden = {
        "line_t": groupstat("line_t"),
        "needle": groupstat("needle"),
        "stage": groupstat("stage"),
    }
    return hidden


def build_payload(src: Path) -> dict:
    """엑셀 -> DATA payload(dict). 데스크톱 앱에서 재사용하기 위해 함수로 분리."""
    # 앱에서 엑셀을 여러 번 불러와도 부트스트랩 CI가 매번 같게 나오도록 난수를 다시 고정
    global RNG
    RNG = np.random.default_rng(0)
    raw = load_raw_workbook(src)
    df = preprocess_dataframe(raw)
    rows = build_rows(df, raw)

    model = build_model(rows)
    stable_rows = [r for r in rows if r["stable"]]
    model["stable"] = build_model(rows, subset_rows=stable_rows)
    model["hidden"] = build_hidden(rows)
    model["validation"] = build_validation(rows)
    model["se"] = build_se_analysis(rows, model)

    dates = sorted(r["date"] for r in rows if r["date"])
    return {
        "rows": rows,
        "model": model,
        "meta": {"n": len(rows), "src": src.name, "span": [dates[0], dates[-1]]},
    }


def inject_into_html(template_html: str, payload: dict) -> str:
    """스타일까지 완성된 대시보드 HTML의 DATA 블록만 새 payload로 교체."""
    new_data = json.dumps(payload, ensure_ascii=False)
    m = re.search(r"const DATA = \{.*?\};\s*\n", template_html, re.S)
    if not m:
        raise ValueError("템플릿에서 'const DATA = {...};' 블록을 찾지 못했습니다.")
    return template_html[: m.start()] + "const DATA = " + new_data + ";\n" + template_html[m.end() :]


def build_dashboard_html(src: Path, template_path: Path) -> str:
    payload = build_payload(src)
    template_html = template_path.read_text(encoding="utf-8")
    return inject_into_html(template_html, payload)


def main():
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("XRF_Te.xlsx")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data.json")

    payload = build_payload(src)
    model = payload["model"]
    stable_rows = [r for r in payload["rows"] if r["stable"]]
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=None), encoding="utf-8")
    print(f"저장: {out.resolve()}  (rows={len(payload['rows'])}, n_fit={model['n_fit']}, r2={model['r2']}, sigma={model['sigma']})")
    print(f"안정화기: rows={len(stable_rows)}, n_fit={model['stable']['n_fit']}, r2={model['stable']['r2']}")
    v = model.get("validation")
    if v:
        print(f"검증(시간순 분리, {v['cutoff']}부터 테스트): 학습 {v['n_train']}건 R2={v['train_r2']} / "
              f"테스트 {v['n_test']}건 R2={v['test_r2']}, 오차 중앙값 x{v['test_med_ratio']}, "
              f"편향 x{v['test_bias_ratio']}, 범위 적중 {v['test_in_band']*100:.0f}%")
        print(f"{v['cv_folds']}-fold 교차검증 R2: {v['cv_r2']} (평균 {v['cv_r2_mean']})")
        w = v["without_se"]
        print(f"  (Se 항 없는 모델로 같은 분리: 테스트 R2={w['test_r2']}, 오차 x{w['test_med_ratio']}, 편향 x{w['test_bias_ratio']})")
        for g in v["by_system"]:
            o = w["by_system"].get(g["system"], {})
            print(f"  테스트 {g['system']} {g['n']}건: 편향 x{g['bias_ratio']} (Se 항 없을 때 x{o.get('bias_ratio')}), "
                  f"오차 x{g['med_ratio']} (x{o.get('med_ratio')})")
    se = model.get("se")
    if se:
        c = model["coef"]
        print(f"Se 도핑 항: seeded x{np.exp(c['seeded']):.2f} {model['ci']['seeded']}, "
              f"se_doped x{np.exp(c['se_doped']):.2f} {model['ci']['se_doped']} (회귀 표본 중 Se 도핑 {se['n_fit_se']}건)")
        for k, g in se["compare"].items():
            print(f"  {k}: n={g['n']}, Se 중앙값 {g['se_med']} at% (검출분 {g['se_med_detected']}), "
                  f"GPC {g['gpc_med']}, 무증착 {g['nodep_rate']*100:.0f}%, CV {g['cv_med']}%")
        print(f"  도핑 cycle vs Se 함량 스피어만 rho={se['rho_cycle']}, 도핑 비율 rho={se['rho_frac']} (n={se['n_rho']}, 캡층 시편 제외)")


if __name__ == "__main__":
    main()
