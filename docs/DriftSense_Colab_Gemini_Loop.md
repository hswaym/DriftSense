# DriftSense: Colab-Only Execution + Gemini CLI Review Loop

Companion to `DriftSense_7Day_Prompt_Playbook.md` (copy it to `docs/plan.md`). Copy this file to `docs/colab_loop.md`.
Where the two conflict, **this file wins** (notebook names, no local pytest, run reports).

Division of labor:
- **Antigravity**: writes code, tests, notebooks. Executes nothing heavy.
- **Colab**: runs everything: dataset build, cleaning, training, evaluation, pytest. Pushes a compact run report to GitHub.
- **Gemini CLI** (local terminal): reads run reports, verifies against acceptance criteria, diagnoses, fixes code. Executes nothing heavy.

---

## 0. The loop

```
Antigravity: build prompt -> code + tests + notebook source
      | git push (main)
Colab: open notebook from GitHub -> Run all
      | notebook runs tests + stage, writes Drive artifacts,
      | pushes small run report to branch colab-runs
Local: python tools/pull_runs.py  (run reports land in runs/)
Gemini CLI: review prompt -> verdict (PASS / PASS_WITH_WARNINGS / FAIL)
      | FAIL: fix prompt -> push -> Colab 99_debug (fast) or rerun notebook
      | PASS: tag phase, next phase
```

Only one tool edits code at a time. Before switching tool: commit, push, `git pull`.

---

## 1. One-time setup

### 1.1 Local (Windows PowerShell ok)
- Fix broken Antigravity plugin (if not done):
```powershell
Rename-Item -Path "$env:USERPROFILE\.gemini\config\plugins\googlecloudtools.datacloud_telemetry" -NewName "googlecloudtools.datacloud_telemetry.bak" -ErrorAction SilentlyContinue
```
- Install Gemini CLI (check current official instructions; usually): `npm install -g @google/gemini-cli`, then run `gemini` inside the repo folder and log in. Check `gemini --help` for flags on your version.
- Repo has `GEMINI.md` (section 3) so Gemini CLI loads project rules automatically.

### 1.2 GitHub token for Colab (one time)
- Create a **fine-grained personal access token**, only this repo, permission Contents: read and write.
- In Colab: left sidebar, Secrets, add `GITHUB_TOKEN`, enable notebook access. Never print it, never paste it in a cell.
- Public repo is simpler for cloning, but the token is still needed to push run reports.

### 1.3 Colab rules
- Runtime: CPU is enough. No GPU.
- Every notebook starts by cloning/pulling the repo and installing `requirements-colab.txt` (section 2.3).
- Drive is the artifact store (`MyDrive/driftsense/artifacts/<scale>/`). Run reports (small) go to GitHub branch `colab-runs`.
- Free Colab disconnects. Notebooks resume: each stage skips if output exists on Drive unless `FORCE=True`.

---

## 2. What P0 builds (the bridge)

### 2.1 Run report layout (written by Colab, per notebook)

```
runs/<scale>/<phase>/
  summary.json        # schema below
  checks.json         # {check_name: "PASS"|"FAIL", ...}
  stdout.log          # captured prints (tail, max 200 KB)
  pytest.txt          # full pytest output (max 200 KB)
  error.txt           # only if an exception happened: full traceback
  env.txt             # python + library versions, git sha
  samples/*.csv       # head(20) of key tables
  figures/*.png       # each under 300 KB
```
No parquet, no data files in run reports. `runs/` is gitignored on `main`; it lives only on branch `colab-runs`.

`summary.json`:
```json
{
  "phase": "p3", "scale": "full", "seed": 42, "runtime_sec": 0,
  "git_sha": "", "notebook": "03_clean_gold_realism",
  "shapes": {"table": [rows, cols]},
  "key_metrics": {"name": 0.0},
  "checks": {"name": "PASS"},
  "pytest": {"passed": 0, "failed": 0, "errors": 0},
  "warnings": [], "artifacts": ["paths on Drive"]
}
```

### 2.2 Python API in `src/driftsense/utils/colab_bridge.py`

```
RunContext(phase, scale, seed)        # context manager
  .require(paths)                     # raise clear error if prior-phase outputs missing ("run notebook 02 first")
  .stage(name, fn, out_path, force)   # resume: skip if out_path exists
  .check(name, passed: bool)          # records PASS/FAIL, never raises
  .metric(name, value)
  .shape(name, df)
  .sample(name, df)                   # saves head(20) CSV
  .figure(name, fig)                  # saves PNG, enforces size cap
  .run_pytest(args)                   # subprocess pytest -q --tb=short, saves pytest.txt, records counts, check "pytest_all_green"
  .finish()                           # prints RESULT SUMMARY, writes run report, pushes it
On exception inside the with-block: write error.txt with traceback, still write report, still push, then re-raise.
push_runs(): clone branch colab-runs into /content/runs_repo (single-branch; create orphan if missing), copy runs/<scale>/<phase>, commit, push (no force). Token from google.colab.userdata. Never log the token.
```

### 2.3 `requirements-colab.txt` (do not reinstall numpy/pandas/scikit-learn/scipy/matplotlib; Colab ships them)
```
polars
duckdb
pyarrow
lightgbm
ruptures
pandera[polars]
pyyaml
plotly
pytest
nbformat
```
(Check pandera polars extra name against current pandera docs.)

### 2.4 Notebook source and build

Agents produce malformed `.ipynb` JSON. Fix: write notebooks as percent-format Python in `notebooks/src/<name>.py` (cells split by `# %%`), then `tools/build_notebooks.py` (nbformat) generates `notebooks/colab/<name>.ipynb`. Both committed. Test: every notebook validates with `nbformat.validate`; regenerated notebooks equal committed ones.

Notebook names (overrides playbook):

| Phase | Notebook |
|---|---|
| p0 | 00_setup_check |
| p1 | 01_sim_core |
| p2 | 02_faults_dirt_build |
| p3 | 03_clean_gold_realism |
| p4 | 04_forecast_conformal |
| p5 | 05_detection |
| p6 | 06_attribution |
| p7 | 07_narrator_experiments |
| p8 | 08_demo_export |
| p9 | 09_repro_check |
| debug | 99_debug (set `PYTEST_ARGS`, runs, pushes report under `runs/<scale>/debug/`) |

Standard cell order in every notebook: Setup (mount Drive, clone/pull, pip install, print versions, `RunContext`) -> Config (`SCALE`, `SEED`, `FORCE`) -> Require inputs -> Tests (`run.run_pytest`) -> Stage runs (visible calls into src) -> Inspect (shapes, samples, plots) -> Checks (`run.check` with exact names from `docs/acceptance.yaml`) -> Save to Drive -> `run.finish()`.

### 2.5 Local tools
- `tools/pull_runs.py`: `git fetch origin colab-runs`, then `git checkout origin/colab-runs -- runs/` (fails with a clear message if the branch does not exist yet).
- `tools/verify_run.py <phase> --scale <scale>`: reads `docs/acceptance.yaml` + `runs/<scale>/<phase>/`; prints a table of required checks (PASS/FAIL/MISSING), metric bounds, suspicious-result rules, presence of `error.txt`, last 40 lines of `stdout.log`. Exit code nonzero if any required check is not PASS, any bound violated, or `error.txt` exists. `--selftest` runs on fixtures in `tests/fixtures/runs/` so it can be validated without Colab.
- `tools/build_notebooks.py`.

### 2.6 `docs/acceptance.yaml`

Single source of truth for check and metric names. Notebooks must use these exact names. Bounds apply at `scale: full` unless noted.

```yaml
global_required: [pytest_all_green]
suspicious_rules:
  - id: S1  # too perfect detection
    when: "key_metrics.event_recall == 1.0 and key_metrics.fp_per_series_day == 0"
  - id: S2  # coverage exactly target suggests calib/test overlap
    when: "key_metrics.coverage_overall == 0.9"
  - id: S3  # attribution implausibly high
    when: "key_metrics.top1_counterfactual > 0.95"
  - id: S4  # cleaning scoring against itself
    when: "all recovery_rate_* == 1.0"
phases:
  p0:
    checks: [imports_ok, versions_printed, no_pretrained_scan_clean, splits_boundaries_ok, bridge_selftest_ok]
  p1:
    checks: [seed_reproducible, acf_24h_peak, acf_168h_peak, storage_monotone, no_nan,
             cost_identity, cost_ordering, column_set_exact, autoscaler_bounds_ok]
  p2:
    checks: [incident_counts_ok, deviation_3sigma_ok, decoys_present, heldout_absent_train_calib,
             dirt_types_all_present, dirt_rates_in_tolerance, clean_truth_hash_stable, magnitude_nonneg,
             confounded_cases_present]
    metrics: {n_incidents_nondecoy: [30, 60], n_decoys: [6, 14]}
  p3:
    checks: [realism_acf_daily, realism_acf_weekly, realism_heavy_tail, realism_top3_share,
             realism_usage_cost_corr, realism_storage_monotone, zero_incident_windows_lost,
             credits_preserved, quarantine_nonempty, leakage_test_pass, silver_pandera_ok,
             gold_pandera_ok, cleaning_idempotent]
    metrics:
      recovery_rate_duplicates: [0.90, 1.0]
      recovery_rate_timezone_shift: [0.90, 1.0]
      recovery_rate_unit_mix: [0.90, 1.0]
      recovery_rate_restatement: [0.90, 1.0]
      recovery_rate_currency_mix: [0.90, 1.0]
      recovery_rate_column_rename: [0.90, 1.0]
      recovery_rate_cpu_glitch: [0.90, 1.0]
      recovery_rate_missing_short_gap: [0.90, 1.0]
  p4:
    checks: [forecasts_no_nan_complete_hours, no_calib_in_train, splits_disjoint_ordered, coverage_within_2pts]
    soft_checks: [gbm_beats_snaive_mae]   # FAIL allowed, becomes warning, must be reported honestly
    metrics: {coverage_overall: [0.88, 0.92]}
  p5:
    checks: [thresholds_calib_only, all_detectors_reported, decoy_fp_reported, heldout_row_present,
             event_matching_unit_tests]
  p6:
    checks: [pvm_sums_ok, controls_exclude_alarmed, rule_table_complete, overspend_nonneg,
             confounded_reported, low_confidence_flag_present]
    metrics: {top1_counterfactual: [0.0, 1.0], top1_correlation: [0.0, 1.0], effect_mape: [0.0, 5.0]}
  p7:
    checks: [narrator_number_provenance, summary_from_csv_only, seeds_differ, tables_labeled_synthetic]
  p8:
    checks: [demo_5_scenarios_render, demo_files_complete, demo_reads_exports_only]
  p9:
    checks: [all_phase_reports_present, summaries_match_expected]
```

Phase `soft_checks` and `metrics` entries are optional per phase. `verify_run.py` treats metrics outside bounds as FAIL, `soft_checks` as warnings.

---

## 3. `GEMINI.md` (repo root; P0 creates it)

```
# DriftSense: Gemini CLI context
Role: reviewer and fixer of Colab run outputs. First read AGENTS.md, docs/contracts.md, docs/plan.md, docs/colab_loop.md, docs/acceptance.yaml.
Execution rule: never run training, dataset builds, simulations, or pytest locally. All execution happens in Colab. Allowed locally: git, ruff, python -m compileall src, python tools/build_notebooks.py, python tools/verify_run.py, python tools/pull_runs.py.
Run reports are in runs/<scale>/<phase>/ (pulled from branch colab-runs). Read summary.json, checks.json, stdout.log, pytest.txt, error.txt, samples/, figures/ for the phase under review.
Review rules:
- Start by running: python tools/pull_runs.py then python tools/verify_run.py <phase> --scale <scale>. Quote its output.
- Never say a phase passes without quoting the check lines and metric values from the run report.
- Never invent numbers. Use only values present in the run report.
- Apply suspicious_rules from docs/acceptance.yaml and the playbook checklist. Treat too-good results as bugs until explained.
- If error.txt exists, diagnose it first.
Fix rules:
- Diagnose root cause from run evidence in two sentences.
- Add a regression test first (it will run in Colab, not locally). Then fix the cause.
- Never weaken a test, assertion, threshold, or acceptance.yaml to pass. If a threshold looks wrong, say so and ask.
- Never change docs/contracts.md silently. State the change.
- Never use pretrained models or external APIs.
- Small commits. git pull before editing. Push when done and tell the user which Colab notebook to rerun.
Review output format:
VERDICT: PASS | PASS_WITH_WARNINGS | FAIL
CHECKS: table copied from verify_run
SUSPICIOUS: rule id + evidence quote, or "none"
ROOT CAUSES (if FAIL): ranked, with evidence
NEXT: exact commands / notebook to rerun
Save the review to docs/reviews/<phase>-<scale>.md.
```

`AGENTS.md` additions (P0 prompt appends these, replacing any line about running tests locally):
```
Execution: all data builds, training, simulation, and pytest run only in Google Colab. Locally only ruff, python -m compileall src, tools/build_notebooks.py, tools/verify_run.py --selftest.
Notebooks are generated from notebooks/src/*.py via tools/build_notebooks.py. Never hand-edit .ipynb.
Check and metric names come from docs/acceptance.yaml. Use them exactly.
Use pathlib. Files use LF line endings. Code must run on Linux (Colab) and not depend on Windows paths.
Mark tests with @pytest.mark.p<N>. Register markers in pytest.ini. Tests must run in under 60 seconds at SCALE=tiny.
```

---

## 4. Antigravity: Colab-only preamble (paste at top of every Antigravity conversation)

```
Follow AGENTS.md, docs/contracts.md, docs/plan.md, docs/colab_loop.md. You write code, tests, and notebook source only. Do NOT execute the pipeline, simulations, model training, or pytest locally; everything runs in Google Colab. Allowed local commands: ruff check, python -m compileall src, python tools/build_notebooks.py, python tools/verify_run.py --selftest. Notebooks are authored as notebooks/src/<name>.py (percent format) and generated to notebooks/colab/<name>.ipynb; never hand-edit .ipynb. Every notebook uses RunContext from driftsense.utils.colab_bridge, uses the exact check and metric names for its phase from docs/acceptance.yaml, runs the full tiny test suite via run.run_pytest, and ends with run.finish() so a run report is pushed to branch colab-runs. Show the plan first and wait for approval. Implement every item in the phase spec; in the plan artifact list each spec item and where it is implemented. Never weaken a test. Do not use any pretrained model or external API. Do not change docs/contracts.md or docs/acceptance.yaml without stating the change. Do not invent metrics. When done, print: files created, and the exact Colab notebook to open.
```

---

## 5. Phase prompts

Per phase: Antigravity build prompt, Colab steps, Gemini CLI review. Phase specs (what to build) live in `docs/plan.md` section 4. Design traps live in `docs/plan.md` section 3. Contracts in `docs/contracts.md`.

### P0: bridge, contracts, scaffold (Day 1)

Do by hand first: put `AGENTS.md`, `docs/plan.md`, `docs/colab_loop.md`, `docs/acceptance.yaml`, `GEMINI.md` in the repo. Create GitHub repo, push.

Antigravity build prompt:
```
Phase P0. Read docs/plan.md section 4 "P0" and docs/colab_loop.md sections 2 and 3. Tasks:
1. Audit existing repo: list modules, flag anything that contradicts docs/contracts.md. Do not run code; read only.
2. Write docs/contracts.md from docs/plan.md section 2. Flag contradictions; do not resolve them silently.
3. Implement src/driftsense/utils/: seed.py, splits.py (time-fraction splits, boundary-safe), summary.py (RESULT SUMMARY printer), colab_bridge.py (RunContext and push_runs exactly as in docs/colab_loop.md section 2.2, including error.txt on exception and size caps).
4. Implement tools/build_notebooks.py, tools/pull_runs.py, tools/verify_run.py (with --selftest and fixtures under tests/fixtures/runs/ covering PASS, FAIL, MISSING, bounds violation, suspicious rule, error.txt).
5. Create configs/base.yaml, configs/scale.yaml (tiny/small/full per contracts), requirements-colab.txt, pytest.ini with markers p0..p9 and slow, .gitignore (data/, artifacts/, runs/), .gitattributes (LF), GEMINI.md and AGENTS.md additions from docs/colab_loop.md.
6. Tests marked p0: no_pretrained scan of src/ (from_pretrained, transformers, torch.hub, anthropic, openai, chronos, timesfm), splits boundary tests, colab_bridge tests that use a temporary local bare git repo as the runs remote (mock the token source), verify_run tests, notebook validity tests.
7. notebooks/src/00_setup_check.py and notebooks/src/99_debug.py, generate their .ipynb. 99_debug has a PYTEST_ARGS variable, runs pytest, pushes report under runs/<scale>/debug/.
Local commands allowed: ruff check, python -m compileall src, python tools/build_notebooks.py, python tools/verify_run.py --selftest.
```
Colab: open `00_setup_check`, Run all. Then local: `python tools/pull_runs.py`.
Gemini CLI review: use section 6 prompt with `phase=p0 scale=tiny`.
Done when: p0 checks PASS. Tag `p0-done`.

### P1: simulator core (Day 1)

Antigravity build prompt:
```
Phase P1. Read docs/plan.md section 4 "P1" and section 3 design traps. Implement sim/world.py, sim/infra.py, sim/pricing.py exactly per the spec and contracts. Tests marked p1 (run in Colab). Notebook notebooks/src/01_sim_core.py at SCALE=small (config cell lets me switch to full): generate world+infra+pricing, plots (traffic, CPU vs requests, instance count, storage, cost by service), sample tables, then record every p1 check from docs/acceptance.yaml with the exact names. Save outputs to Drive artifacts. Persist a no-fault world function for later fault runs.
```
Colab: `01_sim_core` at `SCALE=small`, then pull runs.
Gemini focus: ACF peaks at 24h and 168h real, storage monotone, cost identity tolerance, autoscaler flapping (look at instance-count plot and samples).

### P2: faults + dirt + build (Day 2)

Antigravity build prompt:
```
Phase P2. Read docs/plan.md section 4 "P2" and section 3 traps 9 and 10. Implement sim/faults.py, sim/dirt.py, sim/build.py, configs/faults.yaml, configs/dirt.yaml per spec. magnitude_inr must come from rerunning the world without the fault. Notebook notebooks/src/02_faults_dirt_build.py at SCALE=full: build dataset to Drive, print counts per fault type and split, dirt counts per type, incident plots with window shading, record all p2 checks with exact names. Also write n_incidents_nondecoy and n_decoys metrics. Resume support: skip build if raw/ exists unless FORCE.
```
Colab: `02_faults_dirt_build` at `SCALE=full`.
Gemini focus: egress_spike only in test; clean_truth hash stable; deviation check; confounded cases present; dirt rates not zero.

### P3: cleaning + gold + realism gate (Day 3)

Antigravity build prompt:
```
Phase P3. Read docs/plan.md section 4 "P3" and traps 4-8 and 12. Implement data/clean.py, data/features.py, sim/realism.py, configs/realism.yaml, tests including tests/test_leakage.py (perturb future, features at t unchanged), and notebooks/src/03_clean_gold_realism.py: Section A realism gate on raw clean_truth, Section B cleaning with before/after counts per step and recovery_rate_<type> metrics scored against clean_truth and dirt_log, Section C gold tables and EDA plots (cost over time, service breakdown, usage-cost scatter, seasonality, incident overlay). Record all p3 checks and recovery metrics with exact names. Cleaning must never delete cost spikes or impute cost.
```
Colab: `03_clean_gold_realism` at full. **G1** gate.
Gemini focus: S4 (all recoveries exactly 1.0), incident windows lost, quarantine reasons, idempotency, realism thresholds actually shown.

### P4: forecast + conformal (Day 4)

Antigravity build prompt:
```
Phase P4. Read docs/plan.md section 4 "P4" and traps 1, 3, 4. Implement forecast/baselines.py, gbm.py, conformal.py. Horizon 24h, lags >= 24h only. Notebook notebooks/src/04_forecast_conformal.py: train on train split only, calibrate on calibration split, report MAE/RMSE/sMAPE per series, coverage per series and overall, width, coverage inside vs outside incident windows, plots with band and incident overlay. Record all p4 checks and metrics (coverage_overall, mae_gbm, mae_snaive) with exact names. Save p3/forecasts.parquet per contract.
```
Colab: `04_forecast_conformal` at full. **G2** gate.
Gemini focus: S2, coverage inside incidents far below outside is expected, lags < 24h anywhere, calib rows in training.

### P5: detection (Day 4)

Antigravity build prompt:
```
Phase P5. Read docs/plan.md section 4 "P5" and trap 11. Implement detect/conformal_detector.py, zscore.py, stl.py, iforest.py, eval.py. All thresholds tuned on calibration split only; report on test only; held-out egress_spike as its own row. Notebook notebooks/src/05_detection.py: comparison table, per-fault recall, decoy false alarms, detection delay median and p90, three incident plots with alarm markers. Record all p5 checks with exact names and metrics event_recall, event_precision, event_f1, fp_per_series_day for the conformal detector. Save alarms per contract.
```
Colab: `05_detection` at full.
Gemini focus: S1, tuning function never touches test, alarm double counting, tolerance asymmetry.

### P6: attribution (Day 5)

Antigravity build prompt:
```
Phase P6. Read docs/plan.md section 4 "P5: attribution" (now phase p6) and traps 2 and 9. Implement attribute/pvm.py, changepoint.py, control.py, drivers.py, rank.py, impact.py, correlation baseline. Controls come only from series with no alarm in the window (use p5 alarms); a test must prove ground_truth is never read by attribution code. Notebook notebooks/src/06_attribution.py: evaluate only detected test incidents, report undetected separately; Top-1 and Top-3 for counterfactual-driver and correlation, split into all, overlapping, confounded; effect_mape versus magnitude_inr; CI coverage; PVM waterfall for three incidents. Record all p6 checks and metrics with exact names.
```
Colab: `06_attribution` at full.
Gemini focus: S3, ground truth leakage into controls, pre-period overlapping earlier incidents, confounded row reported honestly.

### P7: narrator + experiments (Day 6)

Antigravity build prompt:
```
Phase P7. Read docs/plan.md section 4 "P6" and "P7" (now phase p7). Implement explain/template_narrator.py with number-provenance test, and experiments/ scripts X1-X5, X7, X8. Notebook notebooks/src/07_narrator_experiments.py: run experiments, X2/X3/X4 over 3 seeds (regenerate data per seed), write CSV and PNG to Drive, generate docs/results_summary.md from the CSVs only, label every table synthetic. Record all p7 checks with exact names. Copy a compact results_summary.md and CSVs (small) into the run report samples.
```
Colab: `07_narrator_experiments` at full. Runtime is long: run in one sitting, it resumes per experiment.
Gemini focus: seeds actually differ (std not zero everywhere), summary built from CSVs.

### P8: demo export (Day 6)

Antigravity build prompt:
```
Phase P8. Read docs/plan.md section 4 "P8". Notebook notebooks/src/08_demo_export.py: export 5 scenarios (storage_leak, deployment_regression, autoscaling_runaway, traffic_surge, one confounded) to Drive demo/, then render the Plotly demo from the exported files only (overview with conformal band and alarms, incident views with PVM waterfall, ranked causes with CI, narrator text, impact, and an hourly replay cell showing when the alarm fires). Record all p8 checks with exact names. Save screenshots (PNG under 300 KB) of each scenario to figures/. Streamlit is out of scope unless I ask.
```
Colab: `08_demo_export`.
Gemini focus: demo reads exports only, each scenario complete, confounded scenario shows both methods.

### P9: final repro check + docs (Day 7)

Antigravity build prompt:
```
Phase P9. Read docs/plan.md section 4 "P9". Write README.md (mermaid architecture, reproduce steps with the notebook order 00-09, limitations), docs/reproducibility.md and the model card using a script that reads values from run reports (runs/full/<phase>/summary.json) and artifacts, with no hand-typed numbers. Notebook notebooks/src/09_repro_check.py: verify every phase report exists on branch colab-runs, compare key metrics against docs/expected_summaries.json (generated from the first full run), record p9 checks.
```
Colab: `09_repro_check` from a **fresh runtime** (Member 2 does this).
Final: Gemini CLI full review, tag `final`.

---

## 6. Gemini CLI prompts

Save as files in `prompts/gemini/` (P0 creates). Use inside `gemini` with `@prompts/gemini/review.md` and then type `phase=p3 scale=full` (verify `@file` works in your version; otherwise paste the text).

### review.md
```
Review the Colab run for the given phase and scale.
1. Run: python tools/pull_runs.py
2. Run: python tools/verify_run.py <phase> --scale <scale> and quote the full output.
3. Read runs/<scale>/<phase>/summary.json, checks.json, pytest.txt, stdout.log (tail), error.txt if present, samples/*.csv, and look at figures/*.png.
4. Compare with docs/acceptance.yaml and the phase spec in docs/plan.md.
5. Apply suspicious_rules and the suspicious-result checklist in docs/plan.md. Treat too-good results as likely bugs. Name the likely leak or bug and the file where to look.
6. Do not invent numbers. Do not run training, pipelines, or pytest locally.
7. Produce the Review output format from GEMINI.md and save it to docs/reviews/<phase>-<scale>.md.
End with exactly one line: NEXT: <what I should do now>.
```

### fix.md
```
Fix the failures found in the last review for the given phase.
1. Read docs/reviews/<phase>-<scale>.md and the run report in runs/<scale>/<phase>/.
2. State the root cause in two sentences with evidence from the run report.
3. Write a regression test that would have caught it (marked @pytest.mark.<phase>). It runs in Colab, not locally.
4. Fix the cause in src/. Do not weaken tests, assertions, thresholds, or docs/acceptance.yaml. If a threshold looks wrong, stop and ask me.
5. Search src/ for the same bug pattern and fix other occurrences.
6. Run only: ruff check, python -m compileall src, python tools/build_notebooks.py.
7. If docs/contracts.md must change, say exactly what and why, and update it.
8. Commit with a clear message and push. Then tell me: rerun notebooks/colab/99_debug with PYTEST_ARGS="<the exact -k or path for the new test>" first, then the phase notebook.
```

### triage.md (for error.txt crashes)
```
The notebook crashed. Read runs/<scale>/<phase>/error.txt and the tail of stdout.log. Identify the failing line in src/ or notebooks/src/. Explain the cause in two sentences. If it is an environment issue (missing package, Colab version), fix requirements-colab.txt or add a guard. If it is a code bug, follow fix.md. Never catch-and-ignore exceptions to hide the failure.
```

### Escalation rule
If Gemini CLI fails the same check twice, stop. Open Antigravity with the review file attached and ask for a plan-first rewrite of the affected module. Commit before switching tools.

---

## 7. Per-phase checklist (do every time)

1. `git pull` locally. Open Antigravity, paste section 4 preamble + the phase build prompt.
2. Read the plan artifact. Check it lists every spec item. Approve.
3. Let agent finish. Run locally: `ruff check` and `python tools/build_notebooks.py`. `git push`.
4. Colab: open `notebooks/colab/<name>.ipynb` from GitHub. Run all. Watch for the final RESULT SUMMARY and "report pushed" line.
5. Local: `python tools/pull_runs.py`.
6. Gemini CLI: review prompt. Read the verdict yourself; open at least one figure.
7. FAIL: fix prompt, push, run `99_debug` (30 seconds) then the phase notebook. PASS: `git tag p<N>-done`.
8. Log the phase in `docs/contributions.md` with date and who did what.

Time budget per phase: build 30-60 min, Colab 5-30 min, review 10 min.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| Push of run report fails in Colab | Check Secret `GITHUB_TOKEN` is enabled for this notebook and has Contents write on the repo. Fallback: notebook zips `runs/` to Drive; download and unzip into local `runs/`. |
| `pull_runs.py` says branch missing | No notebook has pushed yet. Run `00_setup_check` first. |
| Colab disconnects mid-run | Reconnect, Run all. Stages resume from Drive. |
| `pip install` breaks numpy/pandas | Never list them in `requirements-colab.txt`. Restart runtime after install if Colab asks. |
| Notebook JSON invalid | Edit `notebooks/src/*.py`, regenerate with `tools/build_notebooks.py`. |
| Agent runs code locally anyway | Stop it, quote the Colab-only preamble, restart the conversation. |
| Merge conflict between Antigravity and Gemini edits | One writer at a time. Commit and `git pull` before switching tools. |
| Run report huge | Caps: samples 20 rows, figures 300 KB, logs 200 KB tail. Raise a bug if exceeded. |
| Windows path or line-ending errors | Everything runs on Colab (Linux). Locally only light tools. `.gitattributes` forces LF. |

---

## 9. Honesty rules

- Numbers in docs and slides come only from run reports and Drive artifacts.
- Gemini CLI verdicts are saved in `docs/reviews/`. Member 2 spot-checks them against the raw run reports.
- All results labeled synthetic. Attribution is an estimate under stated assumptions, not proof of causation.
