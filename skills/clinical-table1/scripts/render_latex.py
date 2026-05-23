"""Render Table 1 as a standalone LaTeX document (booktabs + threeparttable)."""
from __future__ import annotations
from pathlib import Path


LATEX_ESCAPES = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
    "<": r"\textless{}",
    ">": r"\textgreater{}",
    "±": r"$\pm$",
    "≥": r"$\geq$",
    "≤": r"$\leq$",
    "—": r"---",
    "–": r"--",
}


def _esc(s) -> str:
    if s is None:
        return ""
    s = str(s)
    out = []
    for ch in s:
        out.append(LATEX_ESCAPES.get(ch, ch))
    return "".join(out)


def _design_note(design: str) -> str:
    if design == "RCT":
        return ("Baseline $p$-values omitted per CONSORT 2010 (Moher BMJ 2010;340:c869) "
                "and Senn (Stat Med 1994;13:1715--26). Balance is assessed by SMD.")
    if design in ("Prospective cohort", "Retrospective cohort", "Cross-sectional", "Registry"):
        return ("Observational design. $p$-values unadjusted; interpret with multiple-testing caution. "
                "SMD per Austin (Stat Med 2009;28:3083): $|SMD|\\geq 0.1$ small, $\\geq 0.2$ meaningful.")
    if design == "Case-control":
        return ("Case-control. Selection variables may not be meaningfully compared. "
                "For matched designs, use conditional logistic regression.")
    if design == "Single-arm prospective":
        return "Single-arm: descriptive only; between-group comparisons not applicable."
    return ("Design unspecified. $p$-values are unadjusted and uncorrected for multiple testing.")


def _band_macro(band: str, text: str) -> str:
    text = _esc(text)
    if not band:
        return text
    if band == "ok":
        return r"\textcolor{smdok}{\textbf{" + text + "}}"
    if band == "small":
        return r"\textcolor{smdsmall}{\textbf{" + text + "}}"
    if band == "meaningful":
        return r"\textcolor{smdbig}{\textbf{" + text + "}}"
    return text


def render_latex(rows: list[dict], meta: dict, out_path: str):
    group_levels = meta["group_levels"]
    group_n = meta["group_n"]
    n_grp = len(group_levels)
    show_p = meta["show_p"]

    # Column spec: l for variable, c per group, c c c c for missing/test/p/smd
    col_spec = "l" + "c" * n_grp + "cccc"
    header_cells = ["Variable"] + [
        f"{_esc(g)}\\\\(n={group_n.get(g,0)})" for g in group_levels
    ] + ["Missing", "Test", "$p$", "SMD"]

    header_line = " & ".join(
        ["\\textbf{" + h + "}" if "\\\\" not in h else "\\makecell{\\textbf{" + h + "}}"
         for h in header_cells]
    ) + " \\\\"

    body_lines = []
    for row in rows:
        name = row["name"]
        if row["kind"] == "level":
            cell_name = r"\quad " + _esc(name.lstrip())
        else:
            annot = row.get("annotation", "")
            base = _esc(name)
            if row["kind"] == "categorical_header":
                base = r"\textbf{" + base + "}"
            if annot:
                base += r" {\small\textit{" + _esc(annot) + "}}"
            cell_name = base
        cells = [cell_name]
        for g in group_levels:
            cells.append(_esc(row["per_group"].get(g, "")))
        cells.append(_esc(row["missing"]))
        cells.append(_esc(row["test"]))
        cells.append(_esc(row["p_str"]))
        cells.append(_band_macro(row.get("smd_band", ""), row["smd_str"]))
        body_lines.append(" & ".join(cells) + r" \\")

    body = "\n".join(body_lines)

    design_note = _design_note(meta["study_design"])

    tex = r"""\documentclass[11pt]{article}
\usepackage[a4paper, margin=2cm, landscape]{geometry}
\usepackage{booktabs}
\usepackage{makecell}
\usepackage{xcolor}
\usepackage{threeparttable}
\usepackage{caption}
\usepackage{longtable}
\usepackage[hidelinks]{hyperref}
\definecolor{smdok}{HTML}{15803D}
\definecolor{smdsmall}{HTML}{CA8A04}
\definecolor{smdbig}{HTML}{B91C1C}
\renewcommand{\arraystretch}{1.15}
\setlength{\tabcolsep}{5pt}

\begin{document}

\begin{center}
{\Large\bfseries Table 1.\ Baseline Characteristics}\\[2pt]
\small """ + _esc(meta["input_name"]) + r""" --- grouped by \texttt{""" + _esc(meta["group_var"]) + r"""} \\
\small Study design: """ + _esc(meta["study_design"]) + r""" --- Generated """ + _esc(meta["generated_at"]) + r"""
\end{center}

\smallskip
\noindent\textit{Note.} """ + design_note + r"""

\bigskip

\begin{small}
\begin{longtable}{""" + col_spec + r"""}
\toprule
""" + header_line + r"""
\midrule
\endhead
""" + body + r"""
\bottomrule
\end{longtable}
\end{small}

\bigskip

\noindent\footnotesize\textit{Methods.}\ Continuous variables summarized as mean$\pm$SD or median [IQR] based on skewness ($|$skew$|>1$) and known-skewed lab variables. Tests: Welch $t$ / Mann--Whitney $U$ (2-group); one-way ANOVA / Kruskal--Wallis ($\geq 3$-group). Categorical: $\chi^2$ (expected $\geq 5$), Fisher's exact ($2\times 2$ with small cells), Monte Carlo $\chi^2$ ($r\times c$ with small cells; 10{,}000 simulations). SMD: standardized differences; for $\geq 3$ groups, the maximum pairwise SMD is shown. Color bands: \textcolor{smdok}{\textbf{$<0.10$}}, \textcolor{smdsmall}{\textbf{$0.10$--$<0.20$}}, \textcolor{smdbig}{\textbf{$\geq 0.20$}}.

\medskip

\noindent\footnotesize\textit{Limitations.}\ $p$-values are unadjusted; multiple-testing correction not applied. Table 1 is a descriptive tool, not hypothesis testing. Available-case missingness; MCAR/MAR/MNAR diagnostics are out of scope.

\medskip

\noindent\footnotesize Source: \texttt{""" + _esc(meta["input_name"]) + r"""} (SHA-256 """ + _esc(meta["input_sha256"]) + r"""). Generated by \texttt{clinical-table1}.

\end{document}
"""

    Path(out_path).write_text(tex, encoding="utf-8")
