"""
Statistical helpers for Table 1 (baseline characteristics).

Conventions:
- Continuous normal     -> Welch's t (2-grp) / one-way ANOVA (>=3-grp). Summary: mean +/- SD.
- Continuous non-normal -> Mann-Whitney U (2-grp) / Kruskal-Wallis (>=3-grp). Summary: median [IQR].
- Categorical           -> Chi-square (expected >=5) / Fisher's exact (2x2 with small cells).
                          For r x c (>2x2) with small cells: chi-square with footnote warning.
- SMD: 2-group only.
    * continuous       -> (m1-m2) / sqrt((sd1^2 + sd2^2)/2)
    * binary           -> (p1-p2) / sqrt((p1(1-p1)+p2(1-p2))/2)
    * multi-level cat  -> Yang & Dalton (2012): sqrt((p1-p2)' S^-1 (p1-p2)),
                          S = (S1+S2)/2, S = diag(p) - p p'
                          (vectors of length K-1, drop one level)
- For >=3 groups, SMD is reported as max pairwise SMD (footnoted).

Normality detection:
    |skewness| > 1  -> non-normal
    OR variable name matches known-skewed regex -> non-normal
"""

from __future__ import annotations
import re
import math
import numpy as np
import pandas as pd
from scipy import stats
from typing import Optional


# Lab values commonly skewed; force median[IQR] regardless of computed skewness
KNOWN_SKEWED_PATTERN = re.compile(
    r"(?ix)"
    r"(?:^|[\s_-])(?:"
    r"tg|triglyceride|crp|hscrp|hs[-_]crp|bnp|nt[-_]?pro[-_]?bnp|"
    r"troponin|creatinine|cr|ferritin|ggt|alt|ast|bilirubin|"
    r"hospital[-_]?stay|length[-_]?of[-_]?stay|los|"
    r"time[-_]?to[-_]?|days[-_]?to[-_]?|hours[-_]?to[-_]?|"
    r"duration|wbc|crp_mg|ldh|alp"
    r")(?:[\s_-]|$|\d)"
)


def is_binary_series(s: pd.Series) -> bool:
    """Return True if series has at most 2 non-null unique values."""
    nunique = s.dropna().nunique()
    return nunique <= 2


def is_known_skewed(name: str) -> bool:
    return bool(KNOWN_SKEWED_PATTERN.search(name))


def detect_var_type(
    name: str,
    s: pd.Series,
    forced_non_normal: set[str],
    forced_normal: set[str],
    binary_as_categorical: bool = True,
) -> str:
    """
    Returns one of:
        'normal', 'non_normal', 'binary', 'categorical', 'skip'
    """
    s = s.dropna()
    if len(s) == 0:
        return "skip"

    # Datetime -> skip from Table 1
    if pd.api.types.is_datetime64_any_dtype(s):
        return "skip"

    if pd.api.types.is_numeric_dtype(s):
        # Binary 0/1 numeric -> categorical
        unique_vals = s.unique()
        if binary_as_categorical and len(unique_vals) <= 2:
            return "binary"
        # Forced
        if name in forced_non_normal:
            return "non_normal"
        if name in forced_normal:
            return "normal"
        # Known-skewed lab name
        if is_known_skewed(name):
            return "non_normal"
        # Skewness check
        try:
            sk = float(stats.skew(s, bias=False, nan_policy="omit"))
        except Exception:
            sk = 0.0
        return "non_normal" if abs(sk) > 1 else "normal"

    # Object / categorical
    n_unique = s.nunique()
    if n_unique <= 2:
        return "binary"
    return "categorical"


# ---------- Summaries ----------

def summarize_normal(s: pd.Series) -> dict:
    s = s.dropna()
    return {
        "n": int(s.size),
        "mean": float(s.mean()),
        "sd": float(s.std(ddof=1)) if s.size > 1 else float("nan"),
    }


def summarize_nonnormal(s: pd.Series) -> dict:
    s = s.dropna()
    return {
        "n": int(s.size),
        "median": float(s.median()),
        "q1": float(s.quantile(0.25)),
        "q3": float(s.quantile(0.75)),
    }


def summarize_categorical(s: pd.Series) -> list[dict]:
    """Returns a list of {level, n, pct} ordered by frequency descending."""
    s = s.dropna()
    total = len(s)
    if total == 0:
        return []
    vc = s.value_counts(dropna=True)
    out = []
    for level, n in vc.items():
        out.append({
            "level": str(level),
            "n": int(n),
            "pct": float(n / total * 100.0),
        })
    return out


# ---------- Tests ----------

def test_continuous_2grp(s1: pd.Series, s2: pd.Series, normal: bool) -> tuple[str, float]:
    s1 = s1.dropna().values
    s2 = s2.dropna().values
    if len(s1) < 2 or len(s2) < 2:
        return ("insufficient_n", float("nan"))
    if normal:
        t, p = stats.ttest_ind(s1, s2, equal_var=False, nan_policy="omit")
        return ("Welch t", float(p))
    u, p = stats.mannwhitneyu(s1, s2, alternative="two-sided")
    return ("Mann-Whitney U", float(p))


def test_continuous_multigrp(groups: list[pd.Series], normal: bool) -> tuple[str, float]:
    arrs = [g.dropna().values for g in groups]
    arrs = [a for a in arrs if len(a) >= 2]
    if len(arrs) < 2:
        return ("insufficient_n", float("nan"))
    if normal:
        f, p = stats.f_oneway(*arrs)
        return ("one-way ANOVA", float(p))
    h, p = stats.kruskal(*arrs)
    return ("Kruskal-Wallis", float(p))


def test_categorical(table: np.ndarray) -> tuple[str, float]:
    """
    table: contingency table (rows = levels, cols = groups), counts.
    Returns (test_name, p_value).
    """
    table = np.asarray(table, dtype=float)
    if table.shape[0] < 2 or table.shape[1] < 2:
        return ("insufficient_levels", float("nan"))
    if table.sum() == 0:
        return ("empty", float("nan"))

    # Drop all-zero rows or columns (they collapse the test)
    nonzero_rows = (table.sum(axis=1) > 0)
    nonzero_cols = (table.sum(axis=0) > 0)
    table = table[np.ix_(nonzero_rows, nonzero_cols)]
    if table.shape[0] < 2 or table.shape[1] < 2:
        return ("insufficient_levels", float("nan"))

    # Compute expected; if any < 5, prefer Fisher (only 2x2 in scipy)
    chi2, p, dof, expected = stats.chi2_contingency(table, correction=False)
    small_cells = bool((expected < 5).any())

    if small_cells and table.shape == (2, 2):
        odds_ratio, p_fisher = stats.fisher_exact(table)
        return ("Fisher's exact", float(p_fisher))

    if small_cells:
        # r x c with small expected: chi-square with simulation
        # scipy.stats.chi2_contingency doesn't simulate; use Monte Carlo
        try:
            rng = np.random.default_rng(20260524)
            sim_p = _simulate_chi2_p(table, rng=rng, n_sim=10000)
            return ("Chi-square (MC)", float(sim_p))
        except Exception:
            return ("Chi-square*", float(p))  # asterisk = warn small cells

    return ("Chi-square", float(p))


def _simulate_chi2_p(table: np.ndarray, rng: np.random.Generator, n_sim: int) -> float:
    """Monte Carlo p-value for r x c chi-square (Patefield-like)."""
    table = np.asarray(table, dtype=int)
    row_sums = table.sum(axis=1)
    col_sums = table.sum(axis=0)
    total = int(table.sum())
    if total == 0:
        return float("nan")

    obs_chi2 = _chi2_stat(table)
    count_ge = 0
    for _ in range(n_sim):
        sim = _random_contingency(row_sums, col_sums, total, rng)
        if _chi2_stat(sim) >= obs_chi2:
            count_ge += 1
    return (count_ge + 1) / (n_sim + 1)


def _chi2_stat(table: np.ndarray) -> float:
    chi2, _, _, _ = stats.chi2_contingency(table, correction=False)
    return float(chi2)


def _random_contingency(row_sums, col_sums, total, rng):
    """Generate random contingency table with fixed marginals (simple shuffle approach)."""
    # Build flat assignment: row indices repeated by row_sums, assign to columns shuffled
    rows = np.repeat(np.arange(len(row_sums)), row_sums)
    cols = np.repeat(np.arange(len(col_sums)), col_sums)
    rng.shuffle(cols)
    out = np.zeros((len(row_sums), len(col_sums)), dtype=int)
    for r, c in zip(rows, cols):
        out[r, c] += 1
    return out


# ---------- SMD ----------

def smd_continuous(s1: pd.Series, s2: pd.Series) -> float:
    """SMD for continuous: (m1-m2) / sqrt((sd1^2+sd2^2)/2)."""
    a = s1.dropna().values
    b = s2.dropna().values
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    m1, m2 = a.mean(), b.mean()
    v1, v2 = a.var(ddof=1), b.var(ddof=1)
    denom = math.sqrt((v1 + v2) / 2) if (v1 + v2) > 0 else float("nan")
    if denom == 0 or math.isnan(denom):
        return float("nan")
    return float((m1 - m2) / denom)


def smd_binary(p1: float, p2: float) -> float:
    """SMD for binary: (p1-p2) / sqrt((p1(1-p1)+p2(1-p2))/2)."""
    denom_sq = (p1 * (1 - p1) + p2 * (1 - p2)) / 2
    if denom_sq <= 0:
        return float("nan")
    return float((p1 - p2) / math.sqrt(denom_sq))


def smd_categorical(table: np.ndarray) -> float:
    """
    Yang & Dalton 2012 multi-level SMD.
    table: 2 x K contingency (rows = groups, cols = levels). Counts.
    Returns sqrt((p1-p2)' S^-1 (p1-p2)) on K-1 levels (drop last).
    """
    table = np.asarray(table, dtype=float)
    if table.shape[0] != 2:
        raise ValueError("smd_categorical expects exactly 2 groups (rows).")
    n1 = table[0].sum()
    n2 = table[1].sum()
    if n1 == 0 or n2 == 0:
        return float("nan")
    p1 = table[0] / n1
    p2 = table[1] / n2
    k = len(p1)
    if k < 2:
        return float("nan")
    if k == 2:
        # Equivalent to binary SMD on one level
        return smd_binary(float(p1[0]), float(p2[0]))
    # Drop the last level (linear dependence)
    p1r = p1[:-1]
    p2r = p2[:-1]
    diff = p1r - p2r
    S1 = np.diag(p1r) - np.outer(p1r, p1r)
    S2 = np.diag(p2r) - np.outer(p2r, p2r)
    S = (S1 + S2) / 2.0
    try:
        invS = np.linalg.pinv(S)
        val = float(diff @ invS @ diff)
        if val < 0:
            return float("nan")
        return math.sqrt(val)
    except np.linalg.LinAlgError:
        return float("nan")


def smd_max_pairwise(group_data: list[tuple[str, pd.Series]],
                     vartype: str) -> tuple[float, str]:
    """
    For >=3 groups, return (max |SMD|, "g1 vs g2 label").
    `group_data` is a list of (group_name, series).
    `vartype` is 'normal', 'non_normal', 'binary', or 'categorical'.
    For binary/categorical, series are categorical pandas Series.
    """
    if len(group_data) < 2:
        return (float("nan"), "")
    best = -1.0
    best_label = ""
    for i in range(len(group_data)):
        for j in range(i + 1, len(group_data)):
            ni, si = group_data[i]
            nj, sj = group_data[j]
            if vartype in ("normal", "non_normal"):
                v = smd_continuous(si, sj)
            elif vartype == "binary":
                a = si.dropna()
                b = sj.dropna()
                if len(a) == 0 or len(b) == 0:
                    v = float("nan")
                else:
                    # Find the "positive" level (first sorted)
                    levels = sorted(set(a.unique()) | set(b.unique()), key=lambda x: str(x))
                    pos = levels[-1]  # use the last level as "positive"
                    p1 = (a == pos).mean()
                    p2 = (b == pos).mean()
                    v = smd_binary(float(p1), float(p2))
            elif vartype == "categorical":
                a = si.dropna()
                b = sj.dropna()
                levels = sorted(set(a.unique()) | set(b.unique()), key=lambda x: str(x))
                if len(levels) < 2:
                    v = float("nan")
                else:
                    row1 = np.array([(a == lv).sum() for lv in levels], dtype=float)
                    row2 = np.array([(b == lv).sum() for lv in levels], dtype=float)
                    v = smd_categorical(np.vstack([row1, row2]))
            else:
                v = float("nan")
            if not math.isnan(v) and abs(v) > best:
                best = abs(v)
                best_label = f"{ni} vs {nj}"
    if best < 0:
        return (float("nan"), "")
    return (best, best_label)


def smd_band(smd: float) -> str:
    """Return 'ok', 'small', or 'meaningful' (or '' if NaN)."""
    if smd is None or (isinstance(smd, float) and math.isnan(smd)):
        return ""
    a = abs(smd)
    if a < 0.1:
        return "ok"
    if a < 0.2:
        return "small"
    return "meaningful"
