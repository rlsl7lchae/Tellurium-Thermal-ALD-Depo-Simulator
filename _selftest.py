"""build.bat이 빌드 전에 호출하는 간단한 셀프테스트.

- 레시피 분류 규칙은 항상 검사한다 (예시 레시피명은 표기 형식만 맞춘 임의의 값).
- sample_data/XRF_Te.xlsx 가 있으면 엑셀 → 모델 → 대시보드 HTML 생성까지 검사한다.
  (실험 데이터는 연구실 비공개라 저장소에 없으므로, 없으면 이 단계는 건너뛴다)
"""
import math
from pathlib import Path

from recipe_parser_v2 import parse_recipe

SAMPLE = Path("sample_data/XRF_Te.xlsx")

# ---- 레시피 분류: "doping" 표기가 없어도 GeTe와 Te 사이의 GeSe는 Se 도핑
cases = [
    ("GeTe(40cycle)_GeSe(10cycle)_Te(OEt)4(300cycle)_I_150sccm", "GETE_GESE_THEN_TE", 10.0, None),
    ("GeTe(40cycle)_GeSe doping(10cycle)_Te(OEt)4(300cycle)_3-15-2-15_I_150sccm", "GETE_GESE_THEN_TE", 10.0, None),
    ("GeTe(40cycle)_GeSe doping(20cycle)_Te(OEt)4(300cycle)_GeSe(50cycle)_3-15-2-15_I_150sccm", "GETE_GESE_THEN_TE", 20.0, 50.0),
    ("GeTe_40cycle_Te(OEt)4_300cycle_GeSe(50cycle)_I_150sccm", "GETE_THEN_TE", None, 50.0),   # Te 뒤 GeSe = 캡층
    ("GeTe(40cycle)_GeSe(10cycle)_I_150sccm", "GETE_ONLY", 10.0, None),
    ("GeSe(50cycle)_3-15-2-15_I_150sccm", "GESE_ONLY", None, 50.0),
]
for name, route, dop, cap in cases:
    p = parse_recipe(name)
    assert p.deposition_route == route, f"{name}: {p.deposition_route} != {route}"
    assert p.gese_doping_cycle == dop, f"{name}: doping {p.gese_doping_cycle} != {dop}"
    assert p.post_gese_cap_cycle == cap, f"{name}: cap {p.post_gese_cap_cycle} != {cap}"
print(f"OK  recipe parser ({len(cases)} cases)")

if not SAMPLE.exists():
    print(f"SKIP pipeline test: {SAMPLE} 없음 (실험 데이터 미포함 저장소)")
    raise SystemExit(0)

from build_dashboard_data import build_dashboard_html, build_payload

payload = build_payload(SAMPLE)
model = payload["model"]
v = model.get("validation")
assert v is not None, "검증(학습/테스트 분리) 결과가 비어 있습니다"
assert v["n_train"] > 0 and v["n_test"] > 0, "학습/테스트 표본 수가 0입니다"
assert "without_se" in v and len(v["test_se"]) == v["n_test"], "검증 결과에 Se 항 비교가 없습니다"

# ---- 회귀식에 Se 도핑 항이 들어갔는지
assert "seeded" in model["coef"] and "se_doped" in model["coef"], "회귀 계수에 seeded / se_doped 항이 없습니다"
assert any(k.startswith("se|") for k in model["cv_map"]) or model.get("se") is None, "cv_map에 Se 도핑(se|) 구분이 없습니다"

build_dashboard_html(SAMPLE, Path("template.html"))
print(f"OK  pipeline (train {v['n_train']} / test {v['n_test']}, test median error x{v['test_med_ratio']}, "
      f"Se doping x{math.exp(model['coef']['se_doped']):.2f} {model['ci']['se_doped']})")
