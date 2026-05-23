---
name: clinical-table1
description: 의학연구 tabular 데이터(.xlsx/.csv)에서 baseline characteristics을 비교하는 Table 1을 R(gtsummary) 엔진으로 자동 생성하는 스킬. RCT, prospective/retrospective cohort, case-control, cross-sectional, registry, single-arm 등 연구 디자인을 모두 지원하며 디자인에 따라 p-value 보고 정책(RCT는 CONSORT 2010에 따라 baseline p 숨김)이 자동 분기된다. 연속형은 정규성에 따라 mean±SD(Welch t/ANOVA)와 median[IQR](Mann-Whitney/Kruskal-Wallis)로, 범주형은 n(%)와 chi-square/Fisher's exact로 처리한다. 모든 변수에 대해 SMD(2군은 표준, ≥3군은 max pairwise via {smd} package)를 색 코딩(<0.1 ok / 0.1-0.2 small / ≥0.2 meaningful)으로 표시한다. 단일 gtsummary 파이프라인에서 HTML(gt) + Word(.docx, flextable) + LaTeX(kableExtra, booktabs)을 한 번에 생성한다. 사용자가 "Table 1", "baseline characteristics", "기초통계 표", "환자군 특성 비교" 같은 표현을 임상 데이터(.xlsx/.csv)와 함께 언급하면 적극적으로 트리거하라. Survival analysis, regression, propensity score matching은 대상이 아니다.
---

# Clinical Table 1 — Baseline Characteristics (R / gtsummary)

의학연구 tabular 데이터(.xlsx/.csv)에서 **publishable Table 1** 한 세트 (HTML + Word + LaTeX)를 R `gtsummary` 단일 파이프라인으로 생성한다. 행은 관찰 단위, 열은 변수, 사용자는 비교 대상이 될 **grouping variable**을 지정한다.

## 핵심 차별점

- **R `gtsummary` + `flextable` + `kableExtra`** 기반 — 임상통계 표준 패키지
- **연구 디자인별 p-value 정책 자동 분기** — RCT는 CONSORT 2010 (Moher BMJ 2010;340:c869) 및 Senn (Stat Med 1994;13:1715-26) 권고에 따라 baseline p-value 기본 숨김
- **모든 변수에 SMD 표시** (Austin Stat Med 2009;28:3083) — `{smd}` 패키지로 계산. 색 코딩: <0.1 (ok), 0.1–0.2 (small), ≥0.2 (meaningful)
- **단일 gtsummary 객체에서 3 포맷 동시 생성** — `as_gt() → gtsave()` (HTML), `as_flex_table() → save_as_docx()` (Word), `as_kable_extra(format="latex") → writeLines()` (LaTeX)
- **자동 정규성 판정** — `|skewness| > 1` 또는 사전등록된 known-skewed lab 변수명 매칭 → 자동 median[IQR]
- **자동 검정 선택** — 정규성·군 수·기대 빈도에 따라 t/ANOVA / Mann-Whitney/KW / χ² / Fisher's exact

## 언제 이 스킬을 쓰는가

- 임상연구 분석의 첫 단계 — 군 간 baseline 비교표 제작
- 논문 Methods/Results의 Table 1 직접 사용
- IRB/PI 보고용 baseline summary
- Multi-arm dose-finding 연구의 군별 특성 점검

가설검정 본분석, 생존분석, Cox/로지스틱 회귀, propensity score matching은 본 스킬의 대상이 아니다.

## 핵심 원칙

1. **연구 디자인에 따라 통계 정책이 분기된다**
2. **p-value보다 SMD를 우선** — p-value는 표본크기에 좌우되어 임상 의미를 왜곡할 수 있다
3. **PHI는 출력에 넣지 않는다** — 식별자 컬럼은 정규식 자동 감지 또는 `--id-cols`로 명시하여 표에서 제외
4. **이상치는 알아서 처리하지 않는다** — 입력 데이터의 통계를 그대로 보고. 이상치 처리는 `clinical-eda-report`로 사전 점검

## 실행 흐름

### 0. 입력 확인

다음 항목을 사용자 메시지에서 추출하거나, 없으면 한 번에 묻는다.

- **연구 디자인** (필수): `RCT` / `Prospective cohort` / `Retrospective cohort` / `Case-control` / `Cross-sectional` / `Registry` / `Single-arm prospective` / `Other`
- **Grouping variable** (필수): Table 1의 컬럼이 될 군 분류 변수명
- 선택사항: `stratified-vars` (RCT의 stratified randomization 변수), `exclude-vars` (outcome 변수 등), `non-normal-vars`, `normal-vars`

### 1. 스크립트 호출

`scripts/run_table1.R`를 `Rscript`로 실행한다. R 코드를 새로 짜지 마라.

```bash
Rscript scripts/run_table1.R \
  --input <입력 파일 절대경로> \
  --output-dir <출력 폴더 절대경로> \
  --group-var <grouping 변수명> \
  --study-design "<RCT|Prospective cohort|...|Other 자유텍스트>" \
  [--sheet <xlsx 시트명>] \
  [--id-cols patient_id,name,RRN] \
  [--exclude-vars mace,time_to_mace_months,cv_death,recurrent_mi,stroke,hf_hospitalization,all_cause_death] \
  [--stratified-vars site,age_group] \
  [--non-normal-vars TG,CRP] \
  [--normal-vars age] \
  [--group-order GLP-1,Placebo] \
  [--p-value-policy auto|always|never] \
  [--formats html,docx,latex]
```

**기본 정책**:
- `--p-value-policy auto`: RCT면 p-value 숨김, 나머지는 표시
- `--formats`: 기본 모두 (html, docx, latex)
- `--id-cols` 미지정 시 정규식 `(?i)(id|name|rrn|registration|patient|chart|mrn|phone|address|birth)` 매칭 컬럼은 자동 제외

**Outcome 변수 처리** — Table 1은 baseline만 다뤄야 하므로 outcome 변수는 명시적으로 `--exclude-vars`에 넣어야 한다. 사용자가 outcome 컬럼을 잘 모르겠다고 하면 컬럼명에서 `outcome`, `mace`, `death`, `event`, `time_to_`, `follow`, `_3yr`, `_3y`, `_fu` 같은 키워드 보유 변수를 추론해 안내하라.

### 2. 결과 확인

스크립트 정상 종료 시 stdout 마지막 줄에 `OK <html_path> <docx_path> <tex_path>` 출력. 사용자에게:
1. HTML 경로 (브라우저로 미리보기)
2. Word 경로 (논문 본문에 직접 붙여넣기)
3. LaTeX 경로 (저널 양식에 import)
4. 간단 요약 (N per group, |SMD| ≥ 0.2 변수 개수)

리포트 본문을 채팅에 다시 풀어 쓰지 말 것.

## 의존성

### R (4.0+)

```r
install.packages(c(
  "gtsummary",   # Table 1 core
  "gt",          # HTML output
  "flextable",   # Word output (Light Grid style)
  "kableExtra",  # LaTeX output (booktabs)
  "officer",     # Word document container
  "smd",         # SMD computation (Yang-Dalton multi-level)
  "optparse",    # CLI argument parsing
  "dplyr", "readxl", "readr", "digest"
))
```

설치 후 `Rscript --version`이 작동하면 OK.

## 통계 정책

### 연속형 변수
- **정규성 판정**: `|skewness| > 1` (Bulmer's rule) 또는 known-skewed lab 변수명 매칭 → 비정규 (median[IQR])
- **요약**: 정규 → `mean ± SD`, 비정규 → `median [Q1, Q3]`
- **검정**: gtsummary `add_p()`로 자동 선택
  - 2군 정규 → `t.test` (Welch by default)
  - 2군 비정규 → `wilcox.test` (Mann-Whitney U)
  - ≥3군 정규 → `aov` (one-way ANOVA)
  - ≥3군 비정규 → `kruskal.test`
- **SMD**: `{smd}` 패키지 `smd::smd()` — 2군은 표준 공식, ≥3군은 max pairwise

### 범주형 변수
- **요약**: `n (%)`, 분모는 비결측 n
- **검정**: gtsummary 기본 `chisq.test.no.correct`; 작은 셀 자동 Fisher's exact (gtsummary warning + fallback)
- **SMD**: `{smd}` 패키지 — binary는 표준, multi-level은 Yang & Dalton (2012) generalized formula

### 결측 처리
- 변수마다 available-case 분모 사용. `missing="ifany"`로 결측 있는 변수만 Missing 행 추가.

### Stratified randomization 변수
- `--stratified-vars`로 지정하면 분포만 표시하고 SMD/p-value는 "by design" 표기.

## 출력 포맷

### HTML (`gt::gtsave()`)
- gt 패키지 native HTML
- SMD 색 코딩 (gt::tab_style)
- 헤더에 디자인 설명, 푸터에 methods + limitations + SHA-256

### Word `.docx` (`flextable::save_as_docx()`)
- Light Grid 스타일 (NEJM/JAMA 호환)
- SMD 색 코딩 (flextable::color)
- 9pt 폰트 (논문 본문 복사 시 적당)

### LaTeX (`kableExtra::as_kable_extra(format="latex")`)
- `booktabs` (toprule, midrule, bottomrule)
- `longtable` (페이지 넘김 자동)
- `xcolor` 로 SMD 색 코딩
- standalone `pdflatex` 컴파일 가능

## 자주 발생하는 함정과 대응

**Outcome 변수가 baseline 표에 들어감**: `--exclude-vars`에 넣어야 함. 사용자에게 outcome 컬럼이 무엇인지 확인.

**한국어 컬럼명의 ID 컬럼**: 정규식 자동 감지가 작동하지 않으니 `--id-cols 환자번호,주민번호` 형태로 명시.

**큰 표본 (n > 10,000)에서 모든 p < 0.001**: 정상. SMD 우선 해석.

**Stratified randomization 변수가 SMD에 잡힘**: `--stratified-vars`로 지정.

**xfun 버전 충돌 (flextable 로드 실패)**: `install.packages(c("xfun","knitr","rmarkdown"))` 로 핵심 의존성 갱신 필요.

## 한계 — 사용자에게 명시할 것

- **Descriptive only**: 이 표는 가설검정/인과추론 결과가 아님
- **Multiple testing 보정 없음**: RCT는 처음부터 p 숨김, 관찰연구는 SMD 우선시
- **Post-hoc pairwise 미포함**: ≥3군 omnibus 검정 유의해도 어느 군 쌍인지 별도 분석 필요
- **Propensity matching 전후 표 동시 출력은 v0.2.0 미지원** — v0.3.0+ 계획
- **Time-varying baseline은 지원하지 않음** — baseline = enrollment 시점 가정

## 참고문헌

- Moher D, et al. CONSORT 2010 Explanation and Elaboration. *BMJ* 2010;340:c869.
- Senn S. Testing for baseline balance in clinical trials. *Stat Med* 1994;13:1715–1726.
- Austin PC. Using the standardized difference. *Stat Med* 2009;28:3083–3107.
- Yang D, Dalton JE. A unified approach to measuring the effect size between two groups using SAS. *SAS Global Forum* 2012, Paper 335-2012.
- Sjoberg DD, Whiting K, Curry M, et al. Reproducible Summary Tables with the {gtsummary} Package. *R Journal* 2021;13(1):570–80.
