# MediStat-Table1

의학연구 tabular 데이터(`.xlsx`/`.csv`)에서 **publishable Table 1** (Baseline Characteristics)을 자동 생성하는 Claude Code skill 모음입니다. **HTML + Word(.docx) + LaTeX** 세 가지 포맷을 한 번에 출력합니다.

> A Claude Code skill that generates a publication-ready Table 1 from clinical/medical tabular data, with study-design-aware statistical policy (CONSORT 2010 for RCT, SMD-first for observational), in HTML/Word/LaTeX simultaneously.

> **v0.3.0**: 엔진을 다시 **Python**으로 환원 (← v0.2.0에서 R로 이행했었음). claude.ai 코드 실행 환경 및 일반 사용자 환경에서의 portability를 위해. R 버전이 코드는 짧았지만 R 설치가 없는 환경(claude.ai sandbox, 다수의 cloud notebook)에서는 동작 불가. Python은 거의 모든 환경에 기본 설치되어 있어 "한 번 만들면 어디서든 도는" 원칙을 우선시.

---

## 📦 포함된 Skill

### `clinical-table1`

연구 디자인에 따라 통계 처리가 자동 분기되는 Table 1 생성기. **Python (pandas/scipy/python-docx) 기반**.

**디자인별 정책 자동 분기**:
- **RCT**: baseline p-value 기본 숨김 (CONSORT 2010 / Senn 1994 권고)
- **Observational** (cohort/case-control/cross-sectional/registry): p-value 표시 + multiple testing 경고 + SMD 우선
- **Single-arm**: descriptive only

**자동 통계 처리**:
- **연속형**: `|skewness| > 1` 또는 known-skewed lab 변수명 (TG, CRP, BNP, troponin, creatinine, hsCRP, LOS, ferritin) → median [IQR] / Mann-Whitney·Kruskal-Wallis; 그 외 → mean ± SD / Welch t·one-way ANOVA
- **범주형**: expected ≥ 5 → χ²; 2×2 with small cell → Fisher's exact; r×c with small cell → Monte Carlo χ² (10,000 sim)
- **SMD**: 2군은 표준 공식; ≥3군은 max pairwise SMD; binary는 표준; multi-level은 Yang & Dalton (2012)
- **SMD 색 코딩**: 🟢 < 0.10, 🟡 0.10–0.20, 🔴 ≥ 0.20

**3가지 출력 포맷 동시 생성**:
- **HTML** — Pretendard 폰트 인라인 임베딩, 다크모드, 인쇄/PDF, 단일 자기완결 파일
- **Word (.docx)** — Light Grid 스타일, 색 코딩된 SMD, 9pt (논문 본문 복사용)
- **LaTeX** — `booktabs` + `longtable`, `xcolor` 색 코딩, standalone `pdflatex` 컴파일 가능

---

## 🚀 설치

### 옵션 A — git clone (권장)

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/JeonKH81/MediStat-Table1.git /tmp/medistat-table1
cp -r /tmp/medistat-table1/skills/clinical-table1 ~/.claude/skills/
rm -rf /tmp/medistat-table1
```

### 옵션 B — zip 다운로드

GitHub **Releases** 또는 **Code → Download ZIP** 후:

```bash
unzip MediStat-Table1-main.zip
mkdir -p ~/.claude/skills
cp -r MediStat-Table1-main/skills/clinical-table1 ~/.claude/skills/
```

설치 후 **Claude Code 재시작** 필요.

---

## 💬 사용법 (Claude Code)

```
GLP1_MI_RCT_data.xlsx 으로 group 변수 기준 Table 1 만들어줘. RCT 임상시험이야.
```

또는:

```
/clinical-table1
```

자동 트리거 표현:
- "Table 1", "baseline characteristics", "기초통계 표"
- "환자군 특성 비교", "demographic comparison"
- "RCT baseline", "cohort baseline"

처음 한 번 **연구 디자인** + **grouping 변수**를 확인 후 자동으로 끝.

---

## ⚙️ 직접 CLI 실행

```bash
python3 skills/clinical-table1/scripts/run_table1.py \
  --input /path/to/data.xlsx \
  --output-dir /path/to/out \
  --group-var treatment_arm \
  --study-design RCT \
  [--sheet patient_data] \
  [--id-cols patient_id,name] \
  [--exclude-vars mace,death,time_to_event] \
  [--stratified-vars site,age_group] \
  [--non-normal-vars TG,CRP] \
  [--normal-vars age] \
  [--group-order "Treatment,Control"] \
  [--p-value-policy auto|always|never] \
  [--formats html,docx,latex]
```

| 옵션 | 설명 |
|---|---|
| `--input` | 입력 `.xlsx` / `.csv` 절대경로 (필수) |
| `--output-dir` | 출력 폴더 (필수) |
| `--group-var` | Grouping variable 컬럼명 (필수) |
| `--study-design` | `RCT` / `Prospective cohort` / `Retrospective cohort` / `Case-control` / `Cross-sectional` / `Registry` / `Single-arm prospective` / 자유텍스트 |
| `--sheet` | xlsx 시트명 (기본: 첫 시트) |
| `--id-cols` | 식별자 컬럼 (쉼표 구분; 정규식 자동 감지에 추가) |
| `--exclude-vars` | 분석 제외 변수 (outcome 등) |
| `--include-vars` | 이것만 포함 (다른 모든 변수 제외) |
| `--stratified-vars` | Stratified randomization 변수 — 비교 통계 생략, "by design" 표기 |
| `--non-normal-vars` | 강제 median [IQR] |
| `--normal-vars` | 강제 mean ± SD |
| `--p-value-policy` | `auto` (default, RCT면 숨김) / `always` / `never` |
| `--group-order` | 군 표시 순서 (기본: 알파벳) |
| `--formats` | `html,docx,latex` 중 선택 (기본 모두) |

---

## 📋 요구사항

- Python 3.9+
- `pandas`, `numpy`, `scipy` (표준)
- `python-docx` (`pip install python-docx`) — Word 출력
- LaTeX 컴파일 (선택): `pdflatex` 또는 Overleaf

```bash
pip install pandas numpy scipy python-docx openpyxl
```

한글 폰트(Pretendard 9 weights, SIL OFL 1.1)는 `assets/fonts/`에 번들 포함되어 시스템 폰트 설치 불필요.

> **claude.ai 코드 실행 환경**에서도 그대로 작동합니다 — pandas/numpy/scipy/python-docx 모두 기본 사용 가능.

---

## 🎯 사용 시나리오

- 논문 Methods/Results의 **Table 1 직행** (Word 복붙, LaTeX import)
- RCT primary publication — CONSORT 준수 자동 정책
- 관찰연구 propensity matching 전 baseline 점검 — SMD 우선
- IRB/PI 보고용 baseline summary
- Multi-arm dose-finding 연구 (≥3군 ANOVA/KW 지원)

## ❌ 대상이 아닌 분석

- Survival analysis (Kaplan-Meier, Cox) — MediStat-KM (예정)
- Logistic / linear regression
- Propensity score matching 전후 동시 표
- Time-varying baseline
- Mixed-effects (cluster) Table 1
- Post-hoc pairwise comparison (≥3군 omnibus 후) — v0.4.0+ 계획

가설검정 본분석은 별도 skill 필요.

---

## 🔒 PHI 보호

식별자 컬럼은 정규식 `(?i)(id|name|rrn|registration|patient|chart|mrn|phone|address|birth)` 으로 자동 감지되어 Table 1에서 제외. 한국어 컬럼명은 `--id-cols`로 명시 (예: `--id-cols 환자번호,주민번호`).

---

## 🗒 버전 히스토리

| Version | 엔진 | 비고 |
|---|---|---|
| v0.1.0 | Python | 초기 릴리스 |
| v0.2.0 | R / gtsummary | 코드 축소(1,000→350줄)했으나 R 없는 환경에서 동작 안 함 |
| **v0.3.0** | **Python** | **portability 우선 — Python으로 환원** (현재) |

R 기반 구현(v0.2.0)은 `git checkout v0.2.0`으로 접근 가능합니다. 로컬에 R 환경이 있고 `gtsummary`/`flextable`/`kableExtra`를 선호하는 사용자에게는 그 쪽이 코드가 짧고 검정된 패키지를 사용하므로 유리합니다.

---

## 📚 참고문헌

- Moher D, Hopewell S, Schulz KF, et al. **CONSORT 2010** Explanation and Elaboration. *BMJ* 2010;340:c869.
- Senn S. Testing for baseline balance in clinical trials. *Stat Med* 1994;13:1715–26.
- Austin PC. Using the standardized difference to compare the prevalence of a binary variable. *Stat Med* 2009;28:3083–3107.
- Yang D, Dalton JE. A unified approach to measuring the effect size between two groups using SAS. *SAS Global Forum* 2012, Paper 335-2012.

---

## ⚖️ License

- **Skill 코드**: MIT License (see [LICENSE](LICENSE))
- **번들 폰트 (Pretendard)**: [SIL Open Font License 1.1](skills/clinical-table1/assets/fonts/LICENSE_PRETENDARD.md) — Copyright (c) 2021 Kil Hyung-jin

---

## 🔗 Related skills (MediStat family)

- [MediStat-EDA](https://github.com/JeonKH81/MediStat-EDA) — Clinical EDA report (Python)
- **MediStat-Table1** — Baseline characteristics table (Python, this repo)
- MediStat-KM — Kaplan-Meier / survival (Python lifelines 기반 예정)
