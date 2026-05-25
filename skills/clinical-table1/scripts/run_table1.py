#!/usr/bin/env python3
"""
clinical-table1: generate a Table 1 (baseline characteristics) for clinical
research tabular data. Output in HTML, Word (.docx), and LaTeX.

Usage:
    python3 run_table1.py \
        --input data.xlsx \
        --output-dir ./out \
        --group-var treatment_arm \
        --study-design RCT \
        [--sheet patient_data] \
        [--id-cols patient_id,name] \
        [--exclude-vars MACE,time_to_mace_months,cv_death] \
        [--stratified-vars site,age_group] \
        [--non-normal-vars var1,var2] \
        [--normal-vars var3] \
        [--p-value-policy auto|always|never]
"""

from __future__ import annotations
import argparse
import hashlib
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Local imports
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import stats as st  # noqa: E402
# Renderers imported lazily inside main() so a missing optional dependency
# (e.g., python-docx) doesn't break formats that don't need it.


# Designs where baseline p-values are discouraged (CONSORT 2010 / Senn 1994)
P_DISCOURAGED_DESIGNS = {"RCT"}

# Identifier auto-detection
ID_REGEX = re.compile(
    r"(?i)(^|_)(id|name|rrn|registration|patient|chart|mrn|phone|address|birth)(_|$|\d)"
)


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="Input .xlsx/.csv path")
    ap.add_argument("--output-dir", required=True, help="Directory for output files")
    ap.add_argument("--group-var", required=True, help="Grouping column name")
    ap.add_argument("--study-design", default="",
                    help="RCT | Prospective cohort | Retrospective cohort | Case-control | Cross-sectional | Registry | Single-arm prospective | <free text>")
    ap.add_argument("--sheet", default=None, help="Sheet name (xlsx only)")
    ap.add_argument("--id-cols", default="", help="Comma-separated identifier columns to skip")
    ap.add_argument("--exclude-vars", default="",
                    help="Comma-separated columns to exclude (e.g., outcomes)")
    ap.add_argument("--include-vars", default="",
                    help="Comma-separated columns to include exclusively (overrides exclude)")
    ap.add_argument("--stratified-vars", default="",
                    help="Stratified-randomization variables; shown without comparison stats")
    ap.add_argument("--non-normal-vars", default="",
                    help="Force median[IQR] for these continuous vars")
    ap.add_argument("--normal-vars", default="",
                    help="Force mean±SD for these continuous vars")
    ap.add_argument("--p-value-policy", choices=["auto", "always", "never"], default="auto",
                    help="auto (default) hides p-values for RCT; always/never override.")
    ap.add_argument("--group-order", default="",
                    help="Comma-separated group label order (default: sorted by name)")
    ap.add_argument("--formats", default="html,docx,latex",
                    help="Output formats (comma-separated): html,docx,latex (default: all)")
    return ap.parse_args()


def _split(csv: str) -> list[str]:
    return [x.strip() for x in csv.split(",") if x.strip()]


def _file_sha256_short(path: str, n: int = 12) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:n]


def load_data(path: str, sheet: str | None) -> tuple[pd.DataFrame, list[str]]:
    """Returns (df, sheet_list_if_xlsx)."""
    sheets = []
    if path.lower().endswith(".csv"):
        for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
            try:
                df = pd.read_csv(path, encoding=enc)
                return df, sheets
            except UnicodeDecodeError:
                continue
        raise RuntimeError("Failed to read CSV with utf-8/cp949/euc-kr")
    # xlsx
    xl = pd.ExcelFile(path)
    sheets = xl.sheet_names
    target = sheet or sheets[0]
    if target not in sheets:
        raise RuntimeError(f"Sheet '{target}' not found. Available: {sheets}")
    df = xl.parse(target)
    return df, sheets


def detect_id_cols(columns: list[str], explicit: list[str]) -> set[str]:
    out = set(explicit)
    for c in columns:
        if ID_REGEX.search(c):
            out.add(c)
    return out


def fmt_p(p: float) -> str:
    if p is None or (isinstance(p, float) and (np.isnan(p) or np.isinf(p))):
        return "—"
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


def fmt_smd(s: float) -> str:
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return "—"
    return f"{abs(s):.2f}"


def fmt_mean_sd(m: float, sd: float) -> str:
    if np.isnan(m):
        return "—"
    if np.isnan(sd):
        return f"{m:.2f}"
    return f"{m:.2f} ± {sd:.2f}"


def fmt_median_iqr(med: float, q1: float, q3: float) -> str:
    if np.isnan(med):
        return "—"
    return f"{med:.2f} [{q1:.2f}, {q3:.2f}]"


def fmt_n_pct(n: int, pct: float) -> str:
    return f"{n} ({pct:.1f}%)"


def build_rows(
    df: pd.DataFrame,
    group_var: str,
    group_levels: list[str],
    candidate_vars: list[str],
    forced_non_normal: set[str],
    forced_normal: set[str],
    stratified_vars: set[str],
    show_p: bool,
    show_smd_2grp: bool,
) -> list[dict]:
    """
    Build the rows of Table 1. Each row is a dict with:
        kind: 'continuous' | 'categorical_header' | 'level' | 'binary'
        name, summary_per_group (dict group -> str), n_missing, missing_pct,
        test, p_str, smd_str, smd_band, stratified
    """
    rows = []
    n_groups = len(group_levels)

    for var in candidate_vars:
        if var == group_var:
            continue
        if var not in df.columns:
            continue
        col = df[var]
        n_total = len(col)
        n_missing = int(col.isna().sum())
        miss_pct = n_missing / n_total * 100.0
        miss_str = f"{n_missing} ({miss_pct:.1f}%)" if n_missing > 0 else "0"
        is_strat = var in stratified_vars

        vtype = st.detect_var_type(var, col, forced_non_normal, forced_normal)
        if vtype == "skip":
            continue

        if vtype == "normal":
            per_group_str = {}
            per_group_series = []
            for g in group_levels:
                s = col[df[group_var] == g]
                summ = st.summarize_normal(s)
                per_group_str[g] = fmt_mean_sd(summ["mean"], summ["sd"]) if summ["n"] > 0 else "—"
                per_group_series.append((g, s))
            if is_strat or not show_p:
                test_name, p = ("—", float("nan"))
            else:
                if n_groups == 2:
                    s1 = per_group_series[0][1]
                    s2 = per_group_series[1][1]
                    test_name, p = st.test_continuous_2grp(s1, s2, normal=True)
                else:
                    test_name, p = st.test_continuous_multigrp(
                        [s for _, s in per_group_series], normal=True
                    )
            if is_strat:
                smd_val, smd_lbl = (float("nan"), "")
            elif n_groups == 2 and show_smd_2grp:
                smd_val = st.smd_continuous(per_group_series[0][1], per_group_series[1][1])
                smd_lbl = ""
            else:
                smd_val, smd_lbl = st.smd_max_pairwise(per_group_series, vartype="normal")
            rows.append({
                "kind": "continuous",
                "name": var,
                "annotation": "mean ± SD",
                "per_group": per_group_str,
                "missing": miss_str,
                "test": test_name if not is_strat else "by design",
                "p_str": "—" if is_strat or not show_p else fmt_p(p),
                "smd_str": fmt_smd(smd_val),
                "smd_band": st.smd_band(smd_val),
                "smd_lbl": smd_lbl,
                "stratified": is_strat,
            })

        elif vtype == "non_normal":
            per_group_str = {}
            per_group_series = []
            for g in group_levels:
                s = col[df[group_var] == g]
                summ = st.summarize_nonnormal(s)
                per_group_str[g] = (
                    fmt_median_iqr(summ["median"], summ["q1"], summ["q3"])
                    if summ["n"] > 0 else "—"
                )
                per_group_series.append((g, s))
            if is_strat or not show_p:
                test_name, p = ("—", float("nan"))
            else:
                if n_groups == 2:
                    test_name, p = st.test_continuous_2grp(
                        per_group_series[0][1], per_group_series[1][1], normal=False
                    )
                else:
                    test_name, p = st.test_continuous_multigrp(
                        [s for _, s in per_group_series], normal=False
                    )
            if is_strat:
                smd_val, smd_lbl = (float("nan"), "")
            elif n_groups == 2 and show_smd_2grp:
                smd_val = st.smd_continuous(per_group_series[0][1], per_group_series[1][1])
                smd_lbl = ""
            else:
                smd_val, smd_lbl = st.smd_max_pairwise(per_group_series, vartype="non_normal")
            rows.append({
                "kind": "continuous",
                "name": var,
                "annotation": "median [IQR]",
                "per_group": per_group_str,
                "missing": miss_str,
                "test": test_name if not is_strat else "by design",
                "p_str": "—" if is_strat or not show_p else fmt_p(p),
                "smd_str": fmt_smd(smd_val),
                "smd_band": st.smd_band(smd_val),
                "smd_lbl": smd_lbl,
                "stratified": is_strat,
            })

        elif vtype == "binary":
            non_null = col.dropna()
            levels = sorted(non_null.unique(), key=lambda x: str(x))
            # Use the "positive" level (alphabetically last by convention, often 1 or 'Yes')
            pos = levels[-1] if levels else None
            per_group_str = {}
            per_group_series = []
            counts_for_test = []
            for g in group_levels:
                sub = col[df[group_var] == g]
                non_null_sub = sub.dropna()
                if pos is None or len(non_null_sub) == 0:
                    per_group_str[g] = "—"
                else:
                    n_pos = int((non_null_sub == pos).sum())
                    pct = n_pos / len(non_null_sub) * 100.0
                    per_group_str[g] = fmt_n_pct(n_pos, pct)
                per_group_series.append((g, non_null_sub))
                counts_for_test.append([
                    int((non_null_sub == lv).sum()) for lv in levels
                ])
            if is_strat or not show_p:
                test_name, p = ("—", float("nan"))
            else:
                table = np.array(counts_for_test).T  # rows = levels, cols = groups
                test_name, p = st.test_categorical(table)
            if is_strat:
                smd_val, smd_lbl = (float("nan"), "")
            elif n_groups == 2 and show_smd_2grp:
                a = per_group_series[0][1]
                b = per_group_series[1][1]
                if pos is None or len(a) == 0 or len(b) == 0:
                    smd_val = float("nan")
                else:
                    smd_val = st.smd_binary(float((a == pos).mean()), float((b == pos).mean()))
                smd_lbl = ""
            else:
                smd_val, smd_lbl = st.smd_max_pairwise(per_group_series, vartype="binary")
            label_suffix = f", {pos}" if pos is not None else ""
            rows.append({
                "kind": "binary",
                "name": f"{var}{', ' + str(pos) if (pos is not None and str(pos) not in ('1','True','Yes','yes','y','Y')) else ''}",
                "annotation": "n (%)",
                "per_group": per_group_str,
                "missing": miss_str,
                "test": test_name if not is_strat else "by design",
                "p_str": "—" if is_strat or not show_p else fmt_p(p),
                "smd_str": fmt_smd(smd_val),
                "smd_band": st.smd_band(smd_val),
                "smd_lbl": smd_lbl,
                "stratified": is_strat,
            })

        elif vtype == "categorical":
            non_null = col.dropna()
            levels = sorted(non_null.unique(), key=lambda x: -int((non_null == x).sum()))
            # Header row
            counts_table = []
            per_group_series = []
            for g in group_levels:
                sub = col[df[group_var] == g].dropna()
                per_group_series.append((g, sub))
                counts_table.append([int((sub == lv).sum()) for lv in levels])
            if is_strat or not show_p:
                test_name, p = ("—", float("nan"))
            else:
                table = np.array(counts_table).T
                test_name, p = st.test_categorical(table)
            if is_strat:
                smd_val, smd_lbl = (float("nan"), "")
            elif n_groups == 2 and show_smd_2grp:
                row1 = np.array(counts_table[0], dtype=float)
                row2 = np.array(counts_table[1], dtype=float)
                smd_val = st.smd_categorical(np.vstack([row1, row2]))
                smd_lbl = ""
            else:
                smd_val, smd_lbl = st.smd_max_pairwise(per_group_series, vartype="categorical")
            rows.append({
                "kind": "categorical_header",
                "name": var,
                "annotation": "n (%)",
                "per_group": {g: "" for g in group_levels},
                "missing": miss_str,
                "test": test_name if not is_strat else "by design",
                "p_str": "—" if is_strat or not show_p else fmt_p(p),
                "smd_str": fmt_smd(smd_val),
                "smd_band": st.smd_band(smd_val),
                "smd_lbl": smd_lbl,
                "stratified": is_strat,
            })
            # Level rows
            for lv in levels:
                per_group_str = {}
                for g in group_levels:
                    sub = col[df[group_var] == g].dropna()
                    if len(sub) == 0:
                        per_group_str[g] = "—"
                    else:
                        n_lv = int((sub == lv).sum())
                        pct = n_lv / len(sub) * 100.0
                        per_group_str[g] = fmt_n_pct(n_lv, pct)
                rows.append({
                    "kind": "level",
                    "name": f"  {lv}",
                    "annotation": "",
                    "per_group": per_group_str,
                    "missing": "",
                    "test": "",
                    "p_str": "",
                    "smd_str": "",
                    "smd_band": "",
                    "smd_lbl": "",
                    "stratified": is_strat,
                })

    return rows


def main():
    args = parse_args()
    input_path = os.path.abspath(args.input)
    out_dir = os.path.abspath(args.output_dir)
    os.makedirs(out_dir, exist_ok=True)

    df, sheets = load_data(input_path, args.sheet)

    if args.group_var not in df.columns:
        print(f"FAIL group-var '{args.group_var}' not in columns. Available: {list(df.columns)}")
        sys.exit(2)

    id_cols = detect_id_cols(list(df.columns), _split(args.id_cols))
    excluded = set(_split(args.exclude_vars)) | id_cols | {args.group_var}
    included = _split(args.include_vars)
    stratified = set(_split(args.stratified_vars))
    forced_non_normal = set(_split(args.non_normal_vars))
    forced_normal = set(_split(args.normal_vars))

    # Determine candidate variables
    if included:
        candidate_vars = [c for c in included if c in df.columns and c not in {args.group_var}]
    else:
        candidate_vars = [c for c in df.columns if c not in excluded]

    # Determine group levels and ordering
    group_levels_raw = sorted([g for g in df[args.group_var].dropna().unique()], key=lambda x: str(x))
    user_order = _split(args.group_order)
    if user_order:
        group_levels = [g for g in user_order if g in group_levels_raw]
        # Append any unspecified
        for g in group_levels_raw:
            if g not in group_levels:
                group_levels.append(g)
    else:
        group_levels = group_levels_raw

    if len(group_levels) < 2:
        print(f"WARN single-arm: only one group level ({group_levels}). Producing descriptive Table 1.")

    # P-value policy
    design = args.study_design.strip()
    if args.p_value_policy == "always":
        show_p = True
    elif args.p_value_policy == "never":
        show_p = False
    else:
        show_p = design not in P_DISCOURAGED_DESIGNS

    # SMD always shown by skill policy
    show_smd_2grp = True

    rows = build_rows(
        df=df,
        group_var=args.group_var,
        group_levels=group_levels,
        candidate_vars=candidate_vars,
        forced_non_normal=forced_non_normal,
        forced_normal=forced_normal,
        stratified_vars=stratified,
        show_p=show_p,
        show_smd_2grp=show_smd_2grp,
    )

    # Group sizes
    group_n = {g: int((df[args.group_var] == g).sum()) for g in group_levels}

    meta = {
        "input_path": input_path,
        "input_name": os.path.basename(input_path),
        "sheet": args.sheet or (sheets[0] if sheets else ""),
        "sheets": sheets,
        "n_rows": int(len(df)),
        "n_cols": int(df.shape[1]),
        "study_design": design or "(unspecified)",
        "group_var": args.group_var,
        "group_levels": group_levels,
        "group_n": group_n,
        "stratified_vars": sorted(stratified),
        "p_value_policy": args.p_value_policy,
        "show_p": show_p,
        "id_cols": sorted(id_cols),
        "excluded_vars": sorted(excluded - {args.group_var} - id_cols),
        "input_sha256": _file_sha256_short(input_path),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    fonts_dir = SCRIPT_DIR.parent / "assets" / "fonts"

    formats = _split(args.formats)
    outputs = []
    base = os.path.splitext(os.path.basename(input_path))[0]

    skipped = []

    if "html" in formats:
        try:
            from render_html import render_html  # lazy
            out_html = os.path.join(out_dir, f"{base}_Table1.html")
            render_html(rows, meta, out_html, fonts_dir=fonts_dir)
            outputs.append(out_html)
        except ImportError as e:
            skipped.append(f"html ({e.name} not installed)")

    if "docx" in formats:
        try:
            from render_docx import render_docx  # requires python-docx
            out_docx = os.path.join(out_dir, f"{base}_Table1.docx")
            render_docx(rows, meta, out_docx)
            outputs.append(out_docx)
        except ImportError as e:
            skipped.append(f"docx (python-docx not installed: pip install python-docx)")

    if "latex" in formats:
        try:
            from render_latex import render_latex  # lazy
            out_tex = os.path.join(out_dir, f"{base}_Table1.tex")
            render_latex(rows, meta, out_tex)
            outputs.append(out_tex)
        except ImportError as e:
            skipped.append(f"latex ({e.name} not installed)")

    if skipped:
        print("WARN skipped: " + "; ".join(skipped))

    print("OK " + " ".join(outputs))


if __name__ == "__main__":
    main()
