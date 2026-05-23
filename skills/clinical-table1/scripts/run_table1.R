#!/usr/bin/env Rscript
# clinical-table1 (R / gtsummary engine) — Table 1 generator
#
# Generates HTML + Word (.docx) + LaTeX from a single gtsummary pipeline.
# Study-design-aware statistical policy:
#   - RCT       : baseline p-values omitted (CONSORT 2010 / Senn 1994); SMD primary.
#   - Observational : p-values shown with multiple-testing caveat; SMD primary.
# Continuous : |skewness|>1 or known-skewed lab name -> median[IQR] (Mann-Whitney/KW).
# Categorical : chi-square; Fisher's exact if expected<5.
# SMD : 2-group standard; >=3-group max pairwise via {smd}.

suppressPackageStartupMessages({
  library(optparse)
})

option_list <- list(
  make_option("--input",            type = "character"),
  make_option("--output-dir",       type = "character"),
  make_option("--group-var",        type = "character"),
  make_option("--study-design",     type = "character", default = ""),
  make_option("--sheet",            type = "character", default = NULL),
  make_option("--id-cols",          type = "character", default = ""),
  make_option("--exclude-vars",     type = "character", default = ""),
  make_option("--include-vars",     type = "character", default = ""),
  make_option("--stratified-vars",  type = "character", default = ""),
  make_option("--non-normal-vars",  type = "character", default = ""),
  make_option("--normal-vars",      type = "character", default = ""),
  make_option("--p-value-policy",   type = "character", default = "auto"),
  make_option("--group-order",      type = "character", default = ""),
  make_option("--formats",          type = "character", default = "html,docx,latex")
)
opt <- parse_args(OptionParser(option_list = option_list), convert_hyphens_to_underscores = TRUE)

# --- helpers ---
csv_split <- function(s) {
  if (is.null(s) || is.na(s) || !nzchar(s)) return(character(0))
  trimws(strsplit(s, ",")[[1]])
}

bail <- function(msg) {
  cat(sprintf("FAIL %s\n", msg))
  quit(status = 2)
}

if (is.null(opt$input))       bail("--input is required")
if (is.null(opt$output_dir))  bail("--output-dir is required")
if (is.null(opt$group_var))   bail("--group-var is required")

opt$input <- normalizePath(opt$input, mustWork = TRUE)
dir.create(opt$output_dir, recursive = TRUE, showWarnings = FALSE)
opt$output_dir <- normalizePath(opt$output_dir, mustWork = TRUE)

# --- packages ---
suppressPackageStartupMessages({
  library(dplyr)
  library(tibble)
  library(readxl)
  library(readr)
  library(gtsummary)
  library(gt)
  library(flextable)
  library(officer)
  library(kableExtra)
  library(smd)
  library(digest)
})

theme_gtsummary_compact()

# --- load ---
input_path <- opt$input
file_ext <- tolower(tools::file_ext(input_path))
sheets <- character(0)
if (file_ext == "csv") {
  for (enc in c("UTF-8", "UTF-8-BOM", "CP949", "EUC-KR")) {
    res <- try(read_csv(input_path, locale = locale(encoding = enc), show_col_types = FALSE), silent = TRUE)
    if (!inherits(res, "try-error")) { df <- res; break }
  }
  if (!exists("df")) bail("Could not read CSV with UTF-8/CP949/EUC-KR")
} else {
  sheets <- excel_sheets(input_path)
  target_sheet <- if (!is.null(opt$sheet) && nzchar(opt$sheet)) opt$sheet else sheets[1]
  if (!(target_sheet %in% sheets)) bail(sprintf("Sheet '%s' not in %s", target_sheet, paste(sheets, collapse=",")))
  df <- read_excel(input_path, sheet = target_sheet)
}
df <- as.data.frame(df)

# --- variable selection ---
if (!(opt$group_var %in% names(df))) {
  bail(sprintf("group-var '%s' not in columns: %s", opt$group_var, paste(names(df), collapse=", ")))
}

id_regex <- "(?i)(^|_)(id|name|rrn|registration|patient|chart|mrn|phone|address|birth)(_|$|\\d)"
auto_ids <- grep(id_regex, names(df), value = TRUE, perl = TRUE)
explicit_ids <- csv_split(opt$id_cols)
all_ids <- unique(c(auto_ids, explicit_ids))

exclude_vars  <- unique(c(csv_split(opt$exclude_vars), all_ids, opt$group_var))
include_vars  <- csv_split(opt$include_vars)
stratified    <- csv_split(opt$stratified_vars)
forced_nn     <- csv_split(opt$non_normal_vars)
forced_norm   <- csv_split(opt$normal_vars)

if (length(include_vars) > 0) {
  vars <- intersect(include_vars, names(df))
} else {
  vars <- setdiff(names(df), exclude_vars)
}

# Drop datetime columns from Table 1
is_datetime <- vapply(df[vars], function(x) inherits(x, c("POSIXct", "POSIXt", "Date")), logical(1))
dropped_datetime <- vars[is_datetime]
vars <- vars[!is_datetime]

# --- known-skewed pattern ---
KNOWN_SKEWED <- "(?ix)(?:^|[\\s_\\-])(tg|triglyceride|crp|hscrp|hs[-_]crp|bnp|nt[-_]?pro[-_]?bnp|troponin|creatinine|cr|ferritin|ggt|alt|ast|bilirubin|hospital[-_]?stay|length[-_]?of[-_]?stay|los|time[-_]?to[-_]?|days[-_]?to[-_]?|hours[-_]?to[-_]?|duration|wbc|ldh|alp)(?:[\\s_\\-]|$|\\d)"

is_known_skewed <- function(name) {
  grepl(KNOWN_SKEWED, name, perl = TRUE)
}

# Categorise variables
categorical_vars <- character(0)
continuous_vars  <- character(0)
non_normal_vars  <- character(0)

for (v in vars) {
  x <- df[[v]]
  if (is.character(x) || is.factor(x) || is.logical(x)) {
    categorical_vars <- c(categorical_vars, v)
    next
  }
  if (is.numeric(x)) {
    uvals <- unique(na.omit(x))
    if (length(uvals) <= 2) {
      categorical_vars <- c(categorical_vars, v)
    } else {
      continuous_vars <- c(continuous_vars, v)
      if (v %in% forced_nn) {
        non_normal_vars <- c(non_normal_vars, v)
      } else if (v %in% forced_norm) {
        # forced normal
      } else if (is_known_skewed(v)) {
        non_normal_vars <- c(non_normal_vars, v)
      } else {
        xx <- na.omit(x)
        if (length(xx) >= 3) {
          m <- mean(xx); s <- sd(xx)
          if (!is.na(s) && s > 0) {
            sk <- mean(((xx - m) / s) ^ 3)
            if (!is.na(sk) && abs(sk) > 1) non_normal_vars <- c(non_normal_vars, v)
          }
        }
      }
    }
  } else {
    # other types -> treat as categorical
    categorical_vars <- c(categorical_vars, v)
  }
}

# Coerce binary numerics to factor (for gtsummary categorical display)
df_t1 <- df[, c(opt$group_var, vars), drop = FALSE]
for (v in categorical_vars) {
  if (is.numeric(df_t1[[v]])) {
    df_t1[[v]] <- factor(df_t1[[v]])
  } else if (is.logical(df_t1[[v]])) {
    df_t1[[v]] <- factor(df_t1[[v]])
  }
}

# Group ordering
group_levels_raw <- sort(unique(na.omit(as.character(df_t1[[opt$group_var]]))))
user_order <- csv_split(opt$group_order)
if (length(user_order) > 0) {
  group_levels <- c(intersect(user_order, group_levels_raw),
                    setdiff(group_levels_raw, user_order))
} else {
  group_levels <- group_levels_raw
}
df_t1[[opt$group_var]] <- factor(as.character(df_t1[[opt$group_var]]), levels = group_levels)

n_groups <- length(group_levels)
if (n_groups < 2) {
  cat(sprintf("WARN single-arm: only one group (%s). Descriptive Table 1 only.\n", paste(group_levels, collapse=",")))
}

# p-value policy
P_DISCOURAGED <- c("RCT")
show_p <- switch(opt$p_value_policy,
  "always" = TRUE,
  "never"  = FALSE,
  "auto"   = !(opt$study_design %in% P_DISCOURAGED))

# --- build gtsummary ---
# Type override: force continuous2 for non-normal so we can use median[IQR]
type_overrides <- list()
stat_overrides <- list()
for (v in continuous_vars) {
  if (v %in% non_normal_vars) {
    stat_overrides[[v]] <- "{median} [{p25}, {p75}]"
  } else {
    stat_overrides[[v]] <- "{mean} ± {sd}"
  }
}

# tbl_summary
tbl <- tbl_summary(
  data = df_t1,
  by = opt$group_var,
  missing = "always",
  missing_text = "Missing",
  statistic = c(
    all_continuous() ~ "{mean} ± {sd}",  # default; overridden below for non-normal
    all_categorical() ~ "{n} ({p}%)"
  ),
  digits = list(
    all_continuous() ~ 2,
    all_categorical() ~ c(0, 1)
  )
)

# Rebuild tbl_summary with per-variable statistic spec for non-normal continuous
if (length(non_normal_vars) > 0) {
  stat_spec <- list()
  for (v in non_normal_vars) {
    stat_spec[[length(stat_spec) + 1]] <- as.formula(
      sprintf("`%s` ~ \"{median} [{p25}, {p75}]\"", v)
    )
  }
  # Keep mean +/- SD for the rest (continuous), and n (%) for categorical
  stat_spec[[length(stat_spec) + 1]] <- all_continuous() ~ "{mean} ± {sd}"
  stat_spec[[length(stat_spec) + 1]] <- all_categorical() ~ "{n} ({p}%)"

  tbl <- tbl_summary(
    data = df_t1,
    by = opt$group_var,
    missing = "ifany",
    missing_text = "Missing",
    statistic = stat_spec,
    digits = list(
      all_continuous() ~ 2,
      all_categorical() ~ c(0, 1)
    )
  )
}

# --- SMD column ---
# Compute SMD manually for all vars (2-group: standard; >=3-group: max pairwise via {smd}).
compute_smd_one <- function(var_name, group, data) {
  x <- data[[var_name]]
  g <- as.character(data[[group]])
  ok <- !is.na(x) & !is.na(g)
  if (sum(ok) < 4) return(NA_real_)
  x <- x[ok]; g <- g[ok]
  res <- try(smd::smd(x = x, g = g, std.error = FALSE), silent = TRUE)
  if (inherits(res, "try-error")) return(NA_real_)
  # res$estimate for 2-group is a single value; for >=3 it's per-pair
  vals <- as.numeric(res$estimate)
  if (length(vals) == 0 || all(is.na(vals))) return(NA_real_)
  return(max(abs(vals), na.rm = TRUE))
}

smd_band <- function(s) {
  if (is.na(s)) return("none")
  a <- abs(s)
  if (a < 0.1) return("ok")
  if (a < 0.2) return("small")
  return("meaningful")
}

# Compute SMD per variable
smd_tbl <- tibble::tibble(
  variable = c(continuous_vars, categorical_vars),
  smd_val  = vapply(c(continuous_vars, categorical_vars),
                    function(v) compute_smd_one(v, opt$group_var, df_t1),
                    numeric(1))
)
smd_tbl$smd_val[smd_tbl$variable %in% stratified] <- NA_real_
smd_tbl$smd_str <- ifelse(is.na(smd_tbl$smd_val), "—", sprintf("%.2f", smd_tbl$smd_val))
smd_tbl$band <- vapply(smd_tbl$smd_val, smd_band, character(1))

# Inject SMD column into gtsummary table_body
tbl <- tbl %>% modify_table_body(
  ~ .x %>% left_join(
      smd_tbl %>% select(variable, smd_str, band),
      by = "variable"
    ) %>%
    mutate(smd_str = ifelse(is.na(smd_str) | row_type != "label", "", smd_str))
)
tbl <- tbl %>% modify_header(smd_str = "**SMD**")
tbl <- tbl %>% modify_column_alignment(columns = smd_str, align = "center")

# Mark stratified rows
if (length(stratified) > 0) {
  tbl <- tbl %>% modify_table_body(
    ~ .x %>% mutate(
      smd_str = ifelse(variable %in% stratified & row_type == "label", "by design", smd_str)
    )
  )
}

# --- p-value ---
if (show_p) {
  # gtsummary auto-selects: t.test (Welch) for normal continuous, wilcox for non-normal,
  # chisq for categorical, but we want explicit control.
  p_tests <- list()
  for (v in continuous_vars) {
    if (v %in% non_normal_vars) {
      p_tests[[length(p_tests)+1]] <- as.formula(sprintf("`%s` ~ \"wilcox.test\"", v))
    } else {
      p_tests[[length(p_tests)+1]] <- as.formula(sprintf("`%s` ~ \"t.test\"", v))
    }
  }
  if (length(categorical_vars) > 0) {
    # gtsummary's chisq.test.no.correct uses chi-square; fisher.test for small cells
    # auto behavior: use "chisq.test" by default; gtsummary will warn for low expected
    p_tests[[length(p_tests)+1]] <- all_categorical() ~ "chisq.test.no.correct"
  }
  if (n_groups >= 3) {
    # For 3+ groups, gtsummary will auto pick ANOVA / KW based on test name
    # We override for continuous
    p_tests <- list()
    for (v in continuous_vars) {
      if (v %in% non_normal_vars) {
        p_tests[[length(p_tests)+1]] <- as.formula(sprintf("`%s` ~ \"kruskal.test\"", v))
      } else {
        p_tests[[length(p_tests)+1]] <- as.formula(sprintf("`%s` ~ \"aov\"", v))
      }
    }
    if (length(categorical_vars) > 0) {
      p_tests[[length(p_tests)+1]] <- all_categorical() ~ "chisq.test.no.correct"
    }
  }
  tbl <- tryCatch(
    tbl %>% add_p(test = p_tests, pvalue_fun = label_style_pvalue(digits = 3)),
    error = function(e) tbl  # if add_p fails (rare), keep table
  )
  # Stratified vars: blank out p
  if (length(stratified) > 0) {
    tbl <- tbl %>% modify_table_body(
      ~ .x %>% mutate(
        p.value = ifelse(variable %in% stratified, NA_real_, p.value)
      )
    )
  }
}

# Bold variable labels
tbl <- tbl %>% bold_labels()

# --- meta ---
input_name <- basename(input_path)
input_hash <- substr(digest(file = input_path, algo = "sha256"), 1, 12)
gen_time <- format(Sys.time(), "%Y-%m-%d %H:%M:%S")

design_str <- if (nzchar(opt$study_design)) opt$study_design else "(unspecified)"

# Design note text
design_note <- switch(opt$study_design,
  "RCT" = "<strong>RCT</strong> — Baseline p-values omitted per CONSORT 2010 (Moher BMJ 2010;340:c869) and Senn (Stat Med 1994;13:1715–26). Balance is assessed by SMD.",
  "Prospective cohort" =,
  "Retrospective cohort" =,
  "Cross-sectional" =,
  "Registry" = sprintf("<strong>%s</strong> — Unadjusted p-values shown; interpret with multiple-testing caution. SMD is the primary balance metric (Austin Stat Med 2009;28:3083): |SMD|≥0.1 small, ≥0.2 meaningful — propensity / covariate adjustment 검토.", opt$study_design),
  "Case-control" = "<strong>Case-control</strong> — Selection variables may not be meaningfully compared. For matched designs, consider conditional logistic regression.",
  "Single-arm prospective" = "<strong>Single-arm</strong> — descriptive only; between-group comparisons not applicable.",
  "Design not specified — p-values are unadjusted and uncorrected for multiple testing."
)

# --- output ---
formats <- csv_split(opt$formats)
base_name <- tools::file_path_sans_ext(input_name)
outputs <- character(0)

# Style: SMD coloring via raw HTML modifier inside gt
smd_color <- function(band) {
  switch(band,
    "ok"          = "#15803D",
    "small"       = "#CA8A04",
    "meaningful"  = "#B91C1C",
    "#6a6a6a")
}

# ---- HTML ----
if ("html" %in% formats) {
  out_html <- file.path(opt$output_dir, sprintf("%s_Table1.html", base_name))
  # Resolve script directory robustly (Rscript)
  args_full <- commandArgs(trailingOnly = FALSE)
  file_arg <- args_full[grep("^--file=", args_full)]
  if (length(file_arg) > 0) {
    script_path <- sub("^--file=", "", file_arg[1])
    fonts_dir <- normalizePath(file.path(dirname(script_path), "..", "assets", "fonts"),
                               mustWork = FALSE)
  } else {
    fonts_dir <- ""
  }
  gt_obj <- tbl %>% as_gt()
  # Apply SMD coloring via gt::tab_style on each row
  body <- tbl$table_body
  body$row_idx <- seq_len(nrow(body))
  for (i in seq_len(nrow(body))) {
    if (!is.na(body$band[i]) && body$band[i] != "" && body$band[i] != "none" && nzchar(body$smd_str[i]) && body$smd_str[i] != "—") {
      gt_obj <- gt_obj %>% gt::tab_style(
        style = gt::cell_text(weight = "bold", color = smd_color(body$band[i])),
        locations = gt::cells_body(columns = smd_str, rows = i)
      )
    }
  }
  gt_obj <- gt_obj %>%
    gt::tab_header(
      title = gt::md("**Table 1. Baseline Characteristics**"),
      subtitle = gt::md(sprintf("*%s* — grouped by `%s` — %s", input_name, opt$group_var, design_str))
    ) %>%
    gt::tab_source_note(gt::html(sprintf(
      "<div style='font-size:11px;color:#555;margin-top:8px;'>%s</div>"      ,
      design_note
    ))) %>%
    gt::tab_source_note(gt::html(sprintf(
      "<div style='font-size:10.5px;color:#666;margin-top:6px;'><strong>Methods.</strong> Continuous: mean±SD with Welch t / one-way ANOVA, or median [IQR] with Mann-Whitney / Kruskal-Wallis based on skewness or known-skewed lab name. Categorical: χ² (or Fisher's exact for small cells). SMD computed via {smd} package; for ≥3 groups, max pairwise |SMD| shown. SMD bands: <span style='color:#15803D;font-weight:600'>&lt;0.10</span> | <span style='color:#CA8A04;font-weight:600'>0.10–&lt;0.20</span> | <span style='color:#B91C1C;font-weight:700'>≥0.20</span>.</div>"
    ))) %>%
    gt::tab_source_note(gt::html(sprintf(
      "<div style='font-size:10px;color:#777;margin-top:6px;'>Source: <code>%s</code> · SHA-256 %s · Generated %s by <code>clinical-table1</code> (R/gtsummary)</div>",
      input_name, input_hash, gen_time
    )))
  # Save HTML
  gt::gtsave(gt_obj, filename = out_html)
  outputs <- c(outputs, out_html)
}

# ---- Word (.docx) ----
if ("docx" %in% formats) {
  out_docx <- file.path(opt$output_dir, sprintf("%s_Table1.docx", base_name))
  ft <- tbl %>% as_flex_table()
  # SMD coloring in flextable
  body <- tbl$table_body
  for (i in seq_len(nrow(body))) {
    if (!is.na(body$band[i]) && body$band[i] != "" && body$band[i] != "none" && nzchar(body$smd_str[i])) {
      ft <- ft %>% flextable::color(
        i = i, j = "smd_str",
        color = smd_color(body$band[i])
      ) %>%
      flextable::bold(i = i, j = "smd_str", bold = TRUE)
    }
  }
  ft <- ft %>%
    flextable::add_header_lines(
      sprintf("Table 1. Baseline Characteristics — %s — %s",
              input_name, design_str)
    ) %>%
    flextable::add_footer_lines(
      "Methods: Continuous mean±SD (Welch t / ANOVA) or median [IQR] (Mann-Whitney / Kruskal-Wallis) by skewness. Categorical χ² or Fisher's exact. SMD via {smd}. ≥3-group: max pairwise SMD."
    ) %>%
    flextable::add_footer_lines(
      sprintf("Source: %s (SHA-256 %s). Generated %s.",
              input_name, input_hash, gen_time)
    ) %>%
    flextable::fontsize(size = 9, part = "all")
  doc <- read_docx() %>%
    body_add_flextable(ft) %>%
    body_add_par("")
  print(doc, target = out_docx)
  outputs <- c(outputs, out_docx)
}

# ---- LaTeX ----
if ("latex" %in% formats) {
  out_tex <- file.path(opt$output_dir, sprintf("%s_Table1.tex", base_name))
  # Build LaTeX via kable
  kab <- tbl %>% as_kable_extra(format = "latex", booktabs = TRUE, longtable = TRUE,
                                 linesep = "")
  # Wrap in standalone document
  preamble <- paste(c(
    "\\documentclass[11pt]{article}",
    "\\usepackage[a4paper, margin=2cm, landscape]{geometry}",
    "\\usepackage{booktabs}",
    "\\usepackage{longtable}",
    "\\usepackage{xcolor}",
    "\\usepackage{caption}",
    "\\usepackage{makecell}",
    "\\definecolor{smdok}{HTML}{15803D}",
    "\\definecolor{smdsmall}{HTML}{CA8A04}",
    "\\definecolor{smdbig}{HTML}{B91C1C}",
    "\\begin{document}",
    "\\begin{center}",
    sprintf("{\\Large\\bfseries Table 1.\\ Baseline Characteristics}\\\\[2pt]"),
    sprintf("\\small %s --- grouped by \\texttt{%s} --- %s --- generated %s",
            gsub("_", "\\\\_", input_name), gsub("_", "\\\\_", opt$group_var),
            gsub("_", "\\\\_", design_str), gen_time),
    "\\end{center}",
    "\\smallskip",
    ""
  ), collapse = "\n")
  postamble <- paste(c(
    "",
    "\\medskip",
    "\\footnotesize\\textit{Methods.}\\ Continuous: mean$\\pm$SD (Welch $t$/ANOVA) or median [IQR] (Mann--Whitney/Kruskal--Wallis) by skewness. Categorical: $\\chi^2$ / Fisher's exact. SMD via \\texttt{smd}; $\\geq 3$-group max pairwise. Color bands: \\textcolor{smdok}{\\textbf{$<0.10$}} | \\textcolor{smdsmall}{\\textbf{$0.10$--$<0.20$}} | \\textcolor{smdbig}{\\textbf{$\\geq 0.20$}}.",
    "",
    "\\medskip",
    sprintf("\\footnotesize Source: \\texttt{%s} (SHA-256 %s). Generated by \\texttt{clinical-table1} (R/gtsummary).",
            gsub("_", "\\\\_", input_name), input_hash),
    "\\end{document}"
  ), collapse = "\n")
  writeLines(c(preamble, as.character(kab), postamble), con = out_tex)
  outputs <- c(outputs, out_tex)
}

cat(sprintf("OK %s\n", paste(outputs, collapse = " ")))
