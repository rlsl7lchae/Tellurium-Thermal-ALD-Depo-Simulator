# Te ALD Process Simulator

> **GitHub:** https://github.com/rlsl7lchae/Tellurium-Thermal-ALD-Depo-Simulator

연구실 Te ALD 공정의 XRF 측정 엑셀을 읽어, **공정 조건 → Te 두께·균일도를 예측**하고
모델이 새 데이터에서도 맞는지 **스스로 검증**해 보여주는 Windows 데스크톱 앱입니다.
엑셀을 새로 불러오면 그 자리에서 모델을 다시 계산합니다.

---

## 1. 문제

- 실험 기록이 엑셀 한 시트에 쌓여 있지만, 공정 정보가 **레시피 이름 문자열**에 섞여 있습니다.
  예: `GeTe(48cycle)_GeSe doping(16cycle)_Te(OEt)4(350cycle)_3-15-2-15_I_150sccm`
  → GeTe seed / GeSe 도핑 / Te cycle 수, 펄스 시퀀스, 반응물, Ar 유량이 한 칸에 들어 있음
- 표기가 시기마다 달라(`GeSe doping(10cycle)` → `GeSe(12cycle)`, `Isopropylamin` 오타 등) 수작업 정리가 필요했고,
  조건을 바꾸면 몇 nm가 나올지, 웨이퍼 내 균일도는 어떨지 미리 볼 방법이 없었습니다.

## 2. 방법

| 단계 | 내용 | 파일 |
|---|---|---|
| 파싱 | 레시피명·Pulse Scheme·Working P·Reactant를 구조화. 증착 경로 **10종 분류 체계** (Te 2/4-step, 공반응물 4-step, GeTe only, GeTe→Te, GeTe→GeSe 도핑→Te, GeSe only, TeO₂ 등). GeSe는 **위치로** 도핑(GeTe와 Te 사이)과 캡층(Te 뒤)을 구분 | `recipe_parser_v2.py`, `preprocess_v2.py` |
| 모델 | `ln(GPC) = 상수 + 반응물 + 기판 + 온도구간 + GeTe seed + Se 도핑` 로그선형 회귀. 계수 신뢰구간은 **부트스트랩 1,000회** | `build_dashboard_data.py` |
| 균일도 | 같은 날짜·같은 레시피 반복 측정의 두께 변동계수(CV)를 조건별로 집계 → 컨포멀리티 등급 | 〃 |
| 검증 | **시간순 홀드아웃**(과거로 학습 → 최근 약 20%로 테스트, 같은 날짜는 한쪽에만) + 5-fold 교차검증. Se 도핑 항을 넣기 전/후, 계열별 오차를 같이 계산 | 〃 |
| 앱 | 대시보드(HTML + Chart.js 내장, 인터넷 없이 동작)를 pywebview 창에 띄움. PyInstaller로 exe, Inno Setup으로 설치 프로그램 | `desktop_app.py`, `template.html`, `installer.iss` |

## 3. 결과 (연구실 데이터 309행 기준, 2025-09 ~ 2026-08)

- 회귀 표본 179건, 학습 R² **0.54** — 예측은 대략 ×1.9 / ÷1.9 범위로 해석
- **시간순 검증**: 2026-07-03까지 143건으로 학습 → 이후 새로 측정한 36건으로 테스트
  - 테스트 오차 중앙값 **±27%**, 학습 오차폭 안에 들어온 비율 **92%**
  - 평균 **약 23% 과대예측** → 최근 공정의 성장 속도가 과거보다 낮아진 것을 모델이 따라가지 못함
- **Se 도핑 항 추가**: 같은 GeTe seed 대비 GPC ×0.92 (95% CI 0.81 ~ 1.04, 통계적으로 구분되지 않음)
  - 테스트의 Se 도핑 시편 예측은 오차 ±34% → ±21%로 개선, 대신 GeTe/Te 시편 과대예측이 커짐
  - 도핑 cycle과 Se 함량은 같은 방향(순위상관 ρ ≈ 0.51)이지만, 같은 cycle에서도 Se 함량이 크게 흩어짐
- **GeTe seed**: seed 없음 대비 GPC ×1.7, 두께 CV 약 33% → 4~5%로 균일도가 크게 개선

**한계** — 범주형 변수만 쓰기 때문에 같은 조건 안의 런 간 차이는 설명하지 못합니다.
펄스 포화 곡선(τ = 1.5 s)은 단독 스윕 데이터가 없어 가정값입니다.
XRF 데이터라 전기적 특성(On/Off 전류 등)은 다루지 않습니다.

## 4. 실행 방법

시연은 함께 제출한 영상으로 확인하실 수 있습니다. 직접 실행하려면 (Windows 10/11, Python 3.11 이상):

```bat
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe desktop_app.py
```

앱이 뜨면 오른쪽 위 **📂 엑셀 불러오기**로 아래 형식의 엑셀을 선택합니다.

배포용 빌드:

```bat
build.bat                                   :: 셀프테스트 → PyInstaller → dist\Te_ALD_Simulator\
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss   :: → installer_output\Te_ALD_Simulator_Setup.exe
```

`sample_data\XRF_Te.xlsx`를 넣어 두면 첫 실행 기본 데이터로 exe에 같이 묶입니다 (없으면 빈 화면에서 시작).

## 5. 데이터를 포함하지 않은 이유와 엑셀 형식

실험 데이터는 **연구실에서 공동 측정한 미공개 데이터**라 이 저장소와 실행 파일에 포함하지 않았습니다.
엑셀은 시트 이름 `Te`, 아래 열을 사용합니다 (열 이름 그대로, 행만 추가).

| 열 | 예시 / 설명 |
|---|---|
| `Date` | 실험 날짜 |
| `(Experiment Set)↵Recipe Name` | `GeTe(40cycle)_GeSe(10cycle)_Te(OEt)4(300cycle)_I_150sccm` |
| `Depo. Temp. (℃)` | 90 |
| `Throttle`, `sub.` | `closed`, `SiO2` / `Sapphire` / `TiN` |
| `Pulse Scheme` | `3-15-2-15, 2-15` (블록별로 쉼표 구분) |
| `Working P` | `4torr(closed)/Ar:150sccm` |
| `Reactant` | `Isopropylamine_Ar:150sccm` |
| `thickness (nm)`, `Layer density↵(ug/cm^2)` | XRF 결과 |
| `Ge (at%)`, `Se (at%)`, `Te (at%)` | **분율**로 저장 (0.29 = 29 at%) |
| `cycle#`, `etc.` | 총 cycle 수, 메모 |

GPC는 시트의 GPC 열이 아니라 `두께 × 10 ÷ Te cycle`로 다시 계산합니다.

## 6. 기여 구분

| 구분 | 담당 |
|---|---|
| ALD 증착 실험, XRF 측정 | 연구실 공동 수행 |
| 데이터 정제 규칙 결정 (날짜 오류, 안정화 구간, 무증착 판정, 도핑/캡층 구분 기준) | 본인 |
| 레시피 파서, 회귀·검증 모델, 대시보드, 데스크톱 앱·설치 프로그램 개발 | 본인 (AI 코딩 도구 활용) |

## 파일 구성

| 파일 | 역할 |
|---|---|
| `desktop_app.py` | 앱 진입점 (pywebview 창, 엑셀 불러오기) |
| `app_paths.py` | 실행 위치·사용자 데이터 폴더(%LOCALAPPDATA%) 처리 |
| `recipe_parser_v2.py` | 레시피명·Pulse Scheme 파서, 증착 경로 분류 |
| `preprocess_v2.py` | 엑셀 로드, 압력·유량·기판 정규화, cycle 보정 |
| `build_dashboard_data.py` | 회귀·부트스트랩·검증·Se 도핑 분석 → 대시보드 데이터 |
| `template.html` | 대시보드 화면 (Chart.js 4.4.4 MIT 포함, 데이터 블록은 비어 있음) |
| `_selftest.py` | 빌드 전 동작 확인 (파서 규칙, 데이터가 있으면 전체 파이프라인) |
| `Te_ALD_Simulator.spec`, `build.bat` | PyInstaller 빌드 |
| `installer.iss`, `app.ico` | Inno Setup 설치 프로그램, 아이콘 |
