"""Render Table 1 as a single self-contained Korean HTML file."""
from __future__ import annotations
import base64
import html
from pathlib import Path


def _b64_font(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _font_faces(fonts_dir: Path) -> str:
    """Embed Pretendard Regular (400) and Bold (700) as @font-face."""
    out = []
    pairs = [
        ("Pretendard-Regular.ttf", 400),
        ("Pretendard-Bold.ttf", 700),
    ]
    for fname, weight in pairs:
        p = fonts_dir / fname
        if p.is_file():
            b64 = _b64_font(p)
            out.append(
                f"@font-face {{ font-family: 'Pretendard'; font-style: normal; "
                f"font-weight: {weight}; src: url(data:font/ttf;base64,{b64}) format('truetype'); "
                f"font-display: swap; }}"
            )
    return "\n".join(out)


def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def _design_note(design: str) -> str:
    d = design.strip()
    if d == "RCT":
        return (
            "이 표는 <strong>RCT</strong>의 baseline characteristics입니다. "
            "CONSORT 2010 (Moher D <em>et al.</em>, <em>BMJ</em> 2010;340:c869) 및 "
            "Senn S, <em>Stat Med</em> 1994;13:1715–26 권고에 따라 "
            "<strong>baseline p-value는 기본 숨김</strong>입니다 — 무작위 배정 하에서의 baseline 불균형은 chance만으로 발생하므로 "
            "검정으로 평가하지 않습니다. 대신 <strong>SMD</strong>로 균형을 확인하세요."
        )
    if d in {"Prospective cohort", "Retrospective cohort", "Cross-sectional", "Registry"}:
        return (
            f"이 표는 <strong>{html.escape(d)}</strong>의 baseline characteristics입니다. "
            "관찰연구의 unadjusted p-value는 큰 표본에서는 임상적으로 무의미한 차이도 유의해 보일 수 있고 "
            "multiple testing 보정 없이 해석하면 위험합니다 — "
            "<strong>SMD</strong> (|SMD| ≥ 0.1 small, ≥ 0.2 meaningful; Austin PC, <em>Stat Med</em> 2009;28:3083) 를 함께 보고 "
            "propensity score / 다변량 보정을 검토하세요."
        )
    if d == "Case-control":
        return (
            "이 표는 <strong>Case-control</strong>의 baseline characteristics입니다. "
            "Cases vs Controls 간 차이는 confounder 후보를 식별하는 데 유용하나, "
            "selection criteria에 사용된 변수는 비교 의미가 제한됩니다. matched design이면 conditional logistic을 검토하세요."
        )
    if d == "Single-arm prospective":
        return (
            "<strong>Single-arm</strong> 연구입니다 — 군 간 비교 통계는 제공되지 않습니다. "
            "descriptive 요약만 표시합니다."
        )
    return (
        f"연구 디자인이 명시되지 않았거나 사용자 정의(<em>{html.escape(d) if d else 'unspecified'}</em>)입니다. "
        "p-value는 unadjusted이며 multiple testing 보정 없음에 유의하세요."
    )


def _row_html(r: dict, group_levels: list) -> str:
    kind = r["kind"]
    name_html = _esc(r["name"])
    if kind == "categorical_header":
        name_cell = f'<td class="row-name row-header">{name_html} <span class="annot">{_esc(r["annotation"])}</span></td>'
    elif kind == "level":
        name_cell = f'<td class="row-name row-level">{name_html}</td>'
    else:
        annot = _esc(r["annotation"])
        name_cell = (
            f'<td class="row-name">{name_html}'
            + (f' <span class="annot">{annot}</span>' if annot else "")
            + "</td>"
        )
    group_cells = "".join(
        f'<td class="grp-val">{_esc(r["per_group"].get(g, ""))}</td>' for g in group_levels
    )
    missing_cell = f'<td class="miss">{_esc(r["missing"])}</td>'
    test_cell = f'<td class="test">{_esc(r["test"])}</td>'
    p_cell = f'<td class="p">{_esc(r["p_str"])}</td>'
    smd_class = "smd-" + (r["smd_band"] or "none")
    smd_cell = f'<td class="smd {smd_class}">{_esc(r["smd_str"])}'
    if r.get("smd_lbl"):
        smd_cell += f' <span class="smd-lbl">({_esc(r["smd_lbl"])})</span>'
    smd_cell += "</td>"
    extra = ""
    if r.get("stratified"):
        extra = " row-strat"
    klass = kind.replace("_", "-") + extra
    return f'<tr class="{klass}">{name_cell}{group_cells}{missing_cell}{test_cell}{p_cell}{smd_cell}</tr>'


CSS = """
:root {
  --bg: #ffffff; --fg: #1a1a1a; --muted: #6a6a6a; --border: #e4e4e4;
  --strip: #f6f7f9; --accent: #2563eb; --warn: #b45309; --danger: #b91c1c;
  --ok: #15803d; --small: #ca8a04;
}
[data-theme="dark"] {
  --bg: #111418; --fg: #e6e6e6; --muted: #9aa0a6; --border: #2a2f36;
  --strip: #181c20; --accent: #5b9bff; --warn: #d99b3a; --danger: #ef4444;
  --ok: #4ade80; --small: #fbbf24;
}
* { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0; background: var(--bg); color: var(--fg);
  font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto,
               'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif;
  font-size: 14px; line-height: 1.55;
}
.container { max-width: 1280px; margin: 0 auto; padding: 28px 36px 64px; }
header h1 { margin: 0 0 4px; font-size: 26px; font-weight: 700; letter-spacing: -0.01em; }
header .sub { color: var(--muted); font-size: 13px; }
header .controls { float: right; margin-top: -38px; }
button.ctrl { border: 1px solid var(--border); background: transparent; color: var(--fg);
  padding: 6px 12px; border-radius: 6px; cursor: pointer; font-family: inherit; font-size: 13px; }
button.ctrl + button.ctrl { margin-left: 6px; }
button.ctrl:hover { background: var(--strip); }
.design-note { margin: 20px 0 24px; padding: 12px 16px; background: var(--strip);
  border-left: 3px solid var(--accent); border-radius: 4px; font-size: 13px; }
.meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px; margin: 18px 0 22px; }
.meta-card { padding: 10px 12px; background: var(--strip); border-radius: 6px; }
.meta-card .lab { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }
.meta-card .val { font-size: 15px; font-weight: 600; }

table.t1 { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }
table.t1 thead th { text-align: left; padding: 10px 8px; border-bottom: 2px solid var(--fg);
  font-weight: 600; vertical-align: bottom; }
table.t1 thead th.grp { text-align: center; }
table.t1 thead th .nfont { display: block; font-weight: 400; font-size: 11px; color: var(--muted); }
table.t1 tbody td { padding: 7px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
.row-name { color: var(--fg); }
.row-header { font-weight: 600; }
.row-level { padding-left: 22px !important; color: var(--muted); }
.annot { color: var(--muted); font-size: 11px; font-weight: 400; }
.grp-val, .miss, .p, .smd { text-align: center; font-variant-numeric: tabular-nums; }
.test { color: var(--muted); font-size: 11px; }
.row-strat { background: var(--strip); }
.row-strat .test::after { content: " · stratified"; color: var(--accent); }

.smd-ok { color: var(--ok); font-weight: 600; }
.smd-small { color: var(--small); font-weight: 600; }
.smd-meaningful { color: var(--danger); font-weight: 700; }
.smd-lbl { color: var(--muted); font-size: 10px; font-weight: 400; }

footer { margin-top: 36px; padding-top: 18px; border-top: 1px solid var(--border);
  color: var(--muted); font-size: 12px; }
footer .lim { margin-top: 12px; padding: 10px 14px; background: var(--strip); border-radius: 4px; }

@media print {
  body { background: #fff; color: #000; }
  .ctrl, header .controls { display: none !important; }
  .container { max-width: 100%; padding: 12px; }
  table.t1 { font-size: 11px; }
  table.t1 thead th { border-bottom: 1.5px solid #000; }
  table.t1 tbody td { border-bottom: 0.5px solid #999; }
  .design-note, .meta-card, footer .lim { background: #f6f6f6; }
}
"""

JS = """
(function(){
  function setTheme(t){
    document.documentElement.setAttribute('data-theme', t);
    try { localStorage.setItem('t1theme', t); } catch(e) {}
    var btn = document.getElementById('themebtn');
    if (btn) btn.textContent = (t === 'dark') ? '☀ Light' : '🌙 Dark';
  }
  try {
    var saved = localStorage.getItem('t1theme');
    if (saved === 'dark' || saved === 'light') setTheme(saved);
    else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) setTheme('dark');
    else setTheme('light');
  } catch(e) { setTheme('light'); }
  document.addEventListener('DOMContentLoaded', function(){
    var btn = document.getElementById('themebtn');
    if (btn) btn.addEventListener('click', function(){
      var cur = document.documentElement.getAttribute('data-theme');
      setTheme(cur === 'dark' ? 'light' : 'dark');
    });
    var pbtn = document.getElementById('printbtn');
    if (pbtn) pbtn.addEventListener('click', function(){
      setTheme('light');
      setTimeout(function(){ window.print(); }, 100);
    });
  });
})();
"""


def render_html(rows: list[dict], meta: dict, out_path: str, fonts_dir: Path):
    group_levels = meta["group_levels"]
    group_n = meta["group_n"]

    # Header row
    grp_th_cells = "".join(
        f'<th class="grp">{_esc(g)}<span class="nfont">n = {group_n.get(g, 0)}</span></th>'
        for g in group_levels
    )

    show_p = meta["show_p"]
    p_header = '<th class="p">p</th>' if show_p else '<th class="p">p</th>'
    # Always include p column header even when hidden — values become "—" for RCT

    rows_html = "\n".join(_row_html(r, group_levels) for r in rows)

    meta_cards = "".join([
        f'<div class="meta-card"><div class="lab">Study design</div><div class="val">{_esc(meta["study_design"])}</div></div>',
        f'<div class="meta-card"><div class="lab">Grouping</div><div class="val">{_esc(meta["group_var"])}</div></div>',
        f'<div class="meta-card"><div class="lab">N (rows)</div><div class="val">{meta["n_rows"]:,}</div></div>',
        f'<div class="meta-card"><div class="lab">Variables</div><div class="val">{meta["n_cols"]}</div></div>',
        f'<div class="meta-card"><div class="lab">Sheet</div><div class="val">{_esc(meta.get("sheet") or "(csv)")}</div></div>',
        f'<div class="meta-card"><div class="lab">Generated</div><div class="val">{_esc(meta["generated_at"])}</div></div>',
    ])

    strat_note = ""
    if meta.get("stratified_vars"):
        strat_note = (
            "<p style='font-size:12px;color:var(--muted);margin:6px 0 0'>"
            "Stratified randomization variables (highlighted, no comparison stats): "
            + ", ".join(_esc(v) for v in meta["stratified_vars"])
            + "</p>"
        )

    excluded_note = ""
    if meta.get("id_cols"):
        excluded_note += (
            f"<p style='font-size:12px;color:var(--muted);margin:4px 0 0'>"
            f"ID columns auto-masked: {', '.join(_esc(v) for v in meta['id_cols'])}</p>"
        )
    if meta.get("excluded_vars"):
        excluded_note += (
            f"<p style='font-size:12px;color:var(--muted);margin:4px 0 0'>"
            f"Excluded: {', '.join(_esc(v) for v in meta['excluded_vars'][:30])}"
            + ("…" if len(meta["excluded_vars"]) > 30 else "")
            + "</p>"
        )

    footer = """
    <footer>
      <div><strong>방법</strong>: 연속형 변수는 정규성(|skewness| ≤ 1 및 known-skewed lab 변수 우회)에 따라
        mean ± SD (Welch t-test / one-way ANOVA) 또는 median [IQR] (Mann-Whitney / Kruskal-Wallis)로 요약.
        범주형은 n (%); expected count ≥ 5 → χ², 그렇지 않고 2×2 → Fisher's exact, r×c with small cells → Monte Carlo χ² (10,000 sim).
        SMD: 연속형 (m₁−m₂)/√((SD₁²+SD₂²)/2), binary (p₁−p₂)/√((p₁q₁+p₂q₂)/2),
        multi-level Yang & Dalton (2012) generalized SMD. ≥ 3군에서는 maximum pairwise SMD를 표시.
        SMD band: <span class="smd-ok">&lt; 0.10</span>,
        <span class="smd-small">0.10 – &lt; 0.20</span>,
        <span class="smd-meaningful">≥ 0.20 (보정 검토)</span>.</div>
      <div class="lim"><strong>Limitations</strong> · p-value는 unadjusted이며 multiple comparison 보정 미적용 — 그대로 논문 본문에 옮기지 마세요.
        Table 1은 descriptive 도구이며 가설검정 결과가 아닙니다. 결측 처리는 변수별 available-case 기준이며, 결측 메커니즘(MCAR/MAR/MNAR) 평가는 본 리포트의 범위가 아닙니다.</div>
      <div style="margin-top:10px;">Input: <code>{name}</code> · SHA-256 {hash} · Generated by clinical-table1</div>
    </footer>
    """.format(name=_esc(meta["input_name"]), hash=_esc(meta["input_sha256"]))

    html_doc = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Table 1 · {_esc(meta["input_name"])}</title>
<style>
{_font_faces(fonts_dir)}
{CSS}
</style>
</head>
<body>
<div class="container">
<header>
  <h1>Table 1. Baseline Characteristics</h1>
  <div class="sub">{_esc(meta["input_name"])} · grouped by <code>{_esc(meta["group_var"])}</code></div>
  <div class="controls">
    <button id="themebtn" class="ctrl">🌙 Dark</button>
    <button id="printbtn" class="ctrl">🖨 Print / PDF</button>
  </div>
</header>
<div class="design-note">{_design_note(meta["study_design"])}</div>
<div class="meta">{meta_cards}</div>
{strat_note}
{excluded_note}
<table class="t1">
<thead>
<tr>
  <th class="row-name">Variable</th>
  {grp_th_cells}
  <th class="miss">Missing</th>
  <th class="test">Test</th>
  {p_header}
  <th class="smd">SMD</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
{footer}
</div>
<script>
{JS}
</script>
</body>
</html>"""

    Path(out_path).write_text(html_doc, encoding="utf-8")
