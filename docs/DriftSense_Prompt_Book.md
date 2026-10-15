# DriftSense Prompt Book

Self-contained. Replaces `DriftSense_7Day_Prompt_Playbook.md` and `DriftSense_Colab_Gemini_Loop.md`. Do not keep those in `docs/` (conflicting specs confuse agents).

Project: cost anomaly detection (conformal bands) + attribution (counterfactual) + template explanation, on self-built synthetic dataset DriftBench-v1. No pretrained models. No LLM/API calls.

Tools:
- **Antigravity**: writes code, tests, notebook source. Executes nothing heavy.
- **Google Colab**: runs everything (build, clean, train, pytest). Pushes run reports to GitHub branch `colab-runs`.
- **Gemini CLI**: reads run reports, verifies, diagnoses, fixes code.

Loop per phase:
```
Antigravity build prompt -> push -> Colab Run all (pushes run report)
-> python tools/pull_runs.py -> Gemini CLI review prompt
-> FAIL: Gemini fix prompt -> push -> Colab 99_debug -> rerun notebook
-> PASS: git tag p<N>-done
```
One tool edits code at a time. `git pull` before switching tools.

---

## PART 1. Setup (by hand, 30 minutes)

### 1.1 Accounts and tools
1. Create GitHub repo `driftsense`. Clone locally.
2. Fix broken Antigravity plugin (PowerShell). Reversible:
```powershell
Rename-Item -Path "$env:USERPROFILE\.gemini\config\plugins\googlecloudtools.datacloud_telemetry" -NewName "googlecloudtools.datacloud_telemetry.bak" -ErrorAction SilentlyContinue
```
3. Install Gemini CLI (check current official instructions, usually `npm install -g @google/gemini-cli`). Run `gemini` in the repo folder once and log in. Check `gemini --help` on your version.
4. GitHub token: fine-grained personal access token, only this repo, Contents read and write. In Colab: Secrets, add `GITHUB_TOKEN`, enable notebook access. Never print it.

### 1.2 Create these files by hand (copy blocks below), commit, push
`AGENTS.md`, `GEMINI.md`, `docs/contracts.md`, `docs/acceptance.yaml`, `docs/traps.md`, `prompts/gemini/review.md`, `prompts/gemini/fix.md`, `prompts/gemini/triage.md`.

### `AGENTS.md`
```
# DriftSense agent rules
Project: DriftSense. Python 3.11+. Type hints. Ruff + pytest.
Code lives in src/driftsense as importable modules. Notebooks only call modules, show outputs, run checks.

## Execution contract (Colab-only)
- All data builds, simulation, cleaning, model training, evaluation, and pytest run ONLY in Google Colab.
- Locally allowed: git, ruff check, python -m compileall src, python tools/build_notebooks.py, python tools/verify_run.py (including --selftest), python tools/pull_runs.py.
- Never run the pipeline, simulations, training, or pytest locally. If a task seems to need it, stop and say which Colab notebook should do it.
- Notebooks are authored as notebooks/src/<name>.py (percent format, cells split by "# %%") and generated to notebooks/colab/<name>.ipynb by tools/build_notebooks.py. Never hand-edit .ipynb.
- Every notebook: Setup cell (mount Drive, clone or pull repo, pip install -r requirements-colab.txt, print versions) -> RunContext -> require inputs -> run tests via run.run_pytest -> stage calls into src -> inspect (shapes, samples, plots) -> run.check with exact names from docs/acceptance.yaml -> save to Drive -> run.finish().
- Use pathlib. LF line endings. Code must run on Linux (Colab), not depend on Windows paths.
- Artifact root comes from env DRIFTSENSE_ARTIFACT_ROOT (Colab: /content/drive/MyDrive/driftsense/artifacts), default ./artifacts.
- Tests are marked @pytest.mark.p<N> (markers registered in pytest.ini) and run in under 60 seconds at SCALE=tiny.

## Hard rules
- No pretrained models, no from_pretrained, no hub weights, no LLM or external API calls. tests enforce this.
- All randomness seeded from configs/base.yaml.
- Time-based splits only (utils/splits.py). No leakage. Forecast features use data up to t-24h only, plus calendar flags known in advance.
- Vectorized code (Polars, NumPy). No per-row Python loops on large tables.
- Never delete cost spikes in cleaning; quarantine. Never impute cost silently; mask and flag.
- Never state metrics unless they come from Colab run reports. Never invent numbers.
- Never claim causation from correlation. State limits in docstrings.
- Label synthetic results as synthetic.
- Check and metric names come from docs/acceptance.yaml. Use them exactly.
- Never weaken a test, assertion, or threshold to pass. Never change docs/contracts.md or docs/acceptance.yaml silently; state the change.
- Small commits. Update docs/CHANGELOG.md each phase.
- Explain non-obvious design choices in docstrings.
```

### `GEMINI.md`
```
# DriftSense: Gemini CLI context
Role: reviewer and fixer of Colab run outputs.
First read AGENTS.md, docs/contracts.md, docs/acceptance.yaml, docs/traps.md.
Execution rule: never run training, dataset builds, simulations, or pytest locally. Allowed locally: git, ruff check, python -m compileall src, python tools/build_notebooks.py, python tools/verify_run.py, python tools/pull_runs.py.
Run reports live in runs/<scale>/<phase>/ (pulled from branch colab-runs): summary.json, checks.json, stdout.log, pytest.txt, error.txt, env.txt, samples/, figures/.
Review rules:
- Run python tools/pull_runs.py then python tools/verify_run.py <phase> --scale <scale>. Quote its output.
- Never say a phase passes without quoting check lines and metric values from the run report.
- Never invent numbers. Use only values in the run report.
- Apply suspicious_rules in docs/acceptance.yaml. Treat too-good results as bugs until explained.
- If error.txt exists, diagnose it first.
Fix rules:
- Root cause in two sentences with evidence.
- Add a regression test first (runs in Colab). Then fix the cause.
- Never weaken tests, assertions, thresholds, or acceptance.yaml. If a threshold looks wrong, stop and ask.
- Never change docs/contracts.md silently.
- No pretrained models or external APIs.
- git pull before editing. Small commits. Push. Tell the user which Colab notebook to rerun.
Review output format:
VERDICT: PASS | PASS_WITH_WARNINGS | FAIL
CHECKS: table from verify_run
SUSPICIOUS: rule id + evidence quote, or none
ROOT CAUSES (if FAIL): ranked, with evidence
NEXT: exact commands / notebook to rerun
Save the review to docs/reviews/<phase>-<scale>.md.
```

### `docs/contracts.md`
```
# Contracts (single source of truth; change only by stating the change)

## Conventions
- Timestamps: UTC, timezone-aware, microsecond precision (Polars Datetime("us","UTC")).
- Currency: INR. USD rows converted with fx_usd_inr in configs/base.yaml.
- series_id = ProviderName + "/" + ServiceName. Providers: aws_like, azure_like. Services: compute, database, object_storage, warehouse, cdn_egress, kubernetes (12 series).
- Splits by fraction of the time range, defined once in utils/splits.py: train 0.667, calibration 0.167, test 0.166. Boundaries: train [t0,t1), calib [t1,t2), test [t2,t3].
- Scales (configs/scale.yaml):
  tiny:  21 days,  2 providers, 6 services, 1 resource per service, 1 incident per fault type
  small: 90 days,  2 providers, 6 services, 2 resources per service
  full:  365 days, 2 providers, 6 services, 4 resources per service (~420k raw rows)
- Fault types: deployment_regression, autoscaling_runaway, traffic_surge, storage_leak, instance_upsize, egress_spike (test split only).
- Decoys: sale, month_end, holiday_dip.

## Paths under <artifact_root>/<scale>/
raw/charges/<YYYY-MM>.parquet, raw/events.parquet, raw/ground_truth.parquet, raw/clean_truth.parquet, raw/dirt_log.parquet
silver/charges.parquet, silver/quarantine.parquet, silver/dq_report.md
gold/service_hour.parquet, gold/service_day.parquet
p4/forecasts.parquet, p4/results.json
p5/alarms.parquet, p5/results.json
p6/attribution.parquet, p6/results.json
p7/*.csv, p7/*.png
demo/*

## charges (raw and silver): one row per resource-hour-charge
x_row_id (int64 unique), x_ingest_ts (UTC), x_source_tz (str),
ChargePeriodStart, ChargePeriodEnd, BillingPeriodStart, BillingPeriodEnd,
ProviderName, SubAccountId, ServiceName, ServiceCategory, ResourceId, ResourceType, RegionId,
ChargeCategory (Usage|Credit|Refund|Purchase), ChargeClass, PricingCategory (On-Demand|Committed),
ConsumedQuantity, ConsumedUnit, PricingQuantity, BillingCurrency,
ListCost, ContractedCost, BilledCost, EffectiveCost, Tags,
x_cpu_pct, x_mem_pct, x_requests, x_storage_gb, x_egress_gb, x_instance_count
Invariant on clean Usage rows: ListCost >= ContractedCost >= EffectiveCost. Credit and Refund rows have negative cost.

## events
ts, event_type (deployment|config_change|sale|month_end|holiday|price_change), series_id (nullable), meta (json string)

## ground_truth
incident_id, start, end, series_id, root_cause, propagated_series (list), magnitude_inr, is_decoy, is_overlap, is_confounded
magnitude_inr = total extra cost over [start,end) versus the no-fault world, computed by rerunning the world without the fault.

## dirt_log
x_row_id, dirt_type, original_value, corrupted_value
dirt_type values: missing_hours, duplicates, restatement, timezone_shift, unit_mix, null_resource_id, cpu_glitch, column_rename, tag_noise, currency_mix

## gold/service_hour: one row per (series_id, ts)
series_id, provider, service, ts, cost_inr, credits_inr, requests, cpu_pct, cpu_per_request, instance_count, storage_gb, egress_gb, egress_per_request, unit_price, n_resources_expected, n_resources_reported, is_complete, split
cost_inr = sum of EffectiveCost over Usage rows only; NaN when is_complete is False. Credits/refunds go to credits_inr. Cost is never imputed. Downstream skips incomplete hours.

## p4/forecasts
series_id, ts, y, yhat, lo, hi, model, split, horizon_h

## p5/alarms
alarm_id, series_id, detector, start, end

## p6/attribution
incident_key, series_id, method, rank, candidate_cause, effect_inr, ci_lo, ci_hi, score, low_confidence

## Function signatures
sim.build.build_dataset(scale: str, cfg: dict, out_dir: Path) -> dict[str, Path]
data.clean.run_cleaning(raw_dir: Path, out_dir: Path, cfg: dict) -> dict
data.features.build_gold(silver_dir: Path, out_dir: Path, cfg: dict) -> dict
forecast.gbm.fit_predict(gold: pl.DataFrame, cfg: dict) -> pl.DataFrame
forecast.conformal.calibrate(fc: pl.DataFrame, alpha: float, cfg: dict) -> pl.DataFrame
detect.conformal_detector.detect(fc: pl.DataFrame, k: int) -> pl.DataFrame
detect.eval.match_events(alarms, ground_truth, tol_hours: int) -> dict
attribute.control.synthetic_control(...) -> dict
utils.summary.print_result_summary(d: dict) -> None
```

### `docs/traps.md`
```
# Design traps (agents fall into these)
1. Forecast horizon is 24 hours ahead. Features only from t-24h or earlier. Lag-1 features let the model follow the anomaly and residuals vanish. Allowed: calendar features known in advance (hour_of_week, holiday, sale, month_end). Not allowed: deployments or telemetry at time t.
2. Attribution controls = series with no alarm in the incident window (from detection output). Never choose controls from ground_truth.
3. Conformal quantile: k = ceil((n+1)*(1-alpha)), k-th smallest calibration score; if k > n the interval is infinite. Calibrate per series. Calibration residuals come from a model trained on the train split only.
4. Missing hours: gold marks is_complete=False and cost_inr=NaN. Never fill cost. Detectors and forecasters skip incomplete hours, else missing rows look like false cost dips.
5. Restatements need x_ingest_ts: latest ingest wins per key.
6. Timezone shift: dirt shifts aws_like timestamps and records x_source_tz; cleaning converts back using that column.
7. Schema drift: dirt renames a column on azure_like in later monthly files only; cleaning applies a rename map per file.
8. Rolling features use data shifted by 24h before the window. Leakage test perturbs the future and checks features at t are unchanged.
9. Confounded case: a deployment event with NO real effect plus a real traffic_surge on the same day. True root cause = traffic_surge. Correlation on event flags blames the deployment.
10. egress_spike appears only in the test split. Nothing is tuned or fit on it.
11. Event matching: an alarm is a hit if it starts in [start - tol_hours, end]. One alarm matches at most one incident. Unmatched alarms are false positives. Alarms on decoys are counted separately as decoy false alarms.
12. Validate silver and gold with pandera at every read and write boundary.
13. magnitude_inr comes from a no-fault world rerun, not from noisy data.
14. Never read ground_truth in modeling, detection, or attribution code; only in evaluation code.
```

### `docs/acceptance.yaml`
```yaml
global_required: [pytest_all_green]
suspicious_rules:
  - id: S1   # too-perfect detection
    when: "key_metrics.event_recall == 1.0 and key_metrics.fp_per_series_day == 0"
  - id: S2   # coverage exactly at target suggests calibration and test overlap
    when: "key_metrics.coverage_overall == 0.9"
  - id: S3   # implausibly high attribution
    when: "key_metrics.top1_counterfactual > 0.95"
  - id: S4   # cleaning scored against itself
    when: "all key_metrics.recovery_rate_* == 1.0"
phases:
  p0:
    checks: [imports_ok, versions_printed, no_pretrained_scan_clean, splits_boundaries_ok, bridge_selftest_ok]
  p1:
    checks: [seed_reproducible, acf_24h_peak, acf_168h_peak, storage_monotone, no_nan,
             cost_identity, cost_ordering, column_set_exact, autoscaler_bounds_ok]
  p2:
    checks: [incident_counts_ok, deviation_3sigma_ok, decoys_present, heldout_absent_train_calib,
             dirt_types_all_present, dirt_rates_in_tolerance, clean_truth_hash_stable,
             magnitude_nonneg, confounded_cases_present]
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
    soft_checks: [gbm_beats_snaive_mae]
    metrics: {coverage_overall: [0.88, 0.92]}
  p5:
    checks: [thresholds_calib_only, all_detectors_reported, decoy_fp_reported, heldout_row_present,
             event_matching_unit_tests]
  p6:
    checks: [pvm_sums_ok, controls_exclude_alarmed, rule_table_complete, overspend_nonneg,
             confounded_reported, low_confidence_flag_present, ground_truth_not_read_in_attribution]
    metrics: {top1_counterfactual: [0.0, 1.0], top1_correlation: [0.0, 1.0], effect_mape: [0.0, 5.0]}
  p7:
    checks: [narrator_number_provenance, summary_from_csv_only, seeds_differ, tables_labeled_synthetic]
  p8:
    checks: [demo_5_scenarios_render, demo_files_complete, demo_reads_exports_only]
  p9:
    checks: [all_phase_reports_present, summaries_match_expected]
```

### `prompts/gemini/review.md`
```
Review the Colab run for the phase and scale I give you.
1. Run: python tools/pull_runs.py
2. Run: python tools/verify_run.py <phase> --scale <scale> and quote the full output.
3. Read runs/<scale>/<phase>/summary.json, checks.json, pytest.txt, stdout.log (tail), error.txt if present, samples/*.csv, and view figures/*.png.
4. Compare with docs/acceptance.yaml and docs/traps.md.
5. Apply suspicious_rules. Treat too-good results as likely bugs; name the likely leak or bug and the file to inspect.
6. Do not invent numbers. Do not run training, pipelines, or pytest locally.
7. Output the Review format from GEMINI.md and save it to docs/reviews/<phase>-<scale>.md.
End with exactly one line: NEXT: <what I should do now>.
```

### `prompts/gemini/fix.md`
```
Fix the failures from the last review for the phase and scale I give you.
1. Read docs/reviews/<phase>-<scale>.md and runs/<scale>/<phase>/.
2. State the root cause in two sentences with evidence from the run report.
3. Write a regression test (marked @pytest.mark.<phase>) that would have caught it. It runs in Colab, not locally.
4. Fix the cause in src/. Do not weaken tests, assertions, thresholds, or docs/acceptance.yaml. If a threshold looks wrong, stop and ask me.
5. Search src/ for the same bug pattern and fix other occurrences.
6. Run only: ruff check, python -m compileall src, python tools/build_notebooks.py.
7. If docs/contracts.md must change, say exactly what and why, then update it.
8. Commit, push. Then tell me: run notebooks/colab/99_debug with PYTEST_ARGS set to the new test, then rerun the phase notebook.
```

### `prompts/gemini/triage.md`
```
The notebook crashed. Read runs/<scale>/<phase>/error.txt and the tail of stdout.log. Find the failing line in src/ or notebooks/src/. Explain the cause in two sentences. If it is environment (missing package, Colab version), fix requirements-colab.txt or add a guard. If it is a code bug, follow prompts/gemini/fix.md. Never catch-and-ignore exceptions to hide a failure.
```

---

## PART 2. Antigravity build prompts

How to use: new Antigravity conversation per phase. Attach `AGENTS.md`, `docs/contracts.md`, `docs/acceptance.yaml`, `docs/traps.md` (use @ file mentions). Paste the prompt. Read the plan artifact, confirm it lists every item, approve. After it finishes: `ruff check`, `python tools/build_notebooks.py`, `git push`, run Colab.

If the agent runs pipeline code or pytest locally: stop it, quote the Execution contract in AGENTS.md, restart.

### Prompt P0: bridge + scaffold

```
Follow AGENTS.md. Show the plan first and wait for approval. Phase P0. Implement the repo scaffold and the Colab bridge. Do not run any code except ruff check, python -m compileall src, python tools/build_notebooks.py, python tools/verify_run.py --selftest.

1. Audit: read existing files in the repo, list what exists, flag anything that contradicts docs/contracts.md. Do not fix silently.
2. Create folders: src/driftsense/{sim,data,forecast,detect,attribute,explain,utils}, tests, tests/fixtures/runs, notebooks/src, notebooks/colab, tools, configs, docs/reviews, experiments.
3. Config files: configs/base.yaml (seed 42, artifact_root ./artifacts, fx_usd_inr 83.0, start_date 2025-01-01, alpha 0.10, horizon_h 24), configs/scale.yaml (tiny/small/full per docs/contracts.md), requirements-colab.txt:
   polars, duckdb, pyarrow, lightgbm, ruptures, pandera[polars], pyyaml, plotly, pytest, nbformat (do NOT list numpy, pandas, scikit-learn, scipy, matplotlib; Colab has them), requirements.txt (same plus ruff), pyproject.toml (package driftsense under src/, ruff config), pytest.ini (markers p0..p9 and slow registered), .gitignore (data/, artifacts/, runs/, __pycache__, .ipynb_checkpoints), .gitattributes (* text=auto eol=lf), docs/CHANGELOG.md.
4. src/driftsense/utils/: seed.py (set all seeds from cfg), io.py (artifact path helpers using DRIFTSENSE_ARTIFACT_ROOT), splits.py (time-fraction splits per contracts: function returning t0,t1,t2,t3 and a function assigning a split label to a timestamp column; boundary-safe, tested), summary.py (print_result_summary printing the RESULT SUMMARY block), colab_bridge.py.
5. colab_bridge.py: class RunContext(phase, scale, seed) as a context manager with methods require(paths), stage(name, fn, out_path, force=False) (skip if out_path exists unless force), check(name, passed) (records PASS/FAIL, never raises), metric(name, value), shape(name, df), sample(name, df) (head(20) CSV), figure(name, fig) (PNG, enforce 300 KB cap by lowering dpi), run_pytest(args) (subprocess pytest -q --tb=short; saves full output to pytest.txt with 200 KB cap; parses passed/failed/errors; records check pytest_all_green), finish() (prints RESULT SUMMARY, writes the run report folder runs/<scale>/<phase>/ with summary.json, checks.json, stdout.log (captured prints, 200 KB tail), pytest.txt, env.txt (python and library versions, git sha), then calls push_runs()). On any exception inside the with-block: write error.txt with the full traceback, still write the report and push, then re-raise. push_runs(): clone branch colab-runs single-branch into /content/runs_repo (create an orphan branch if missing), copy runs/<scale>/<phase>, commit, push without force; token from google.colab.userdata GITHUB_TOKEN (fall back to env GITHUB_TOKEN); never log the token; retry once on push conflict with pull --rebase. summary.json schema: phase, scale, seed, runtime_sec, git_sha, notebook, shapes, key_metrics, checks, pytest {passed,failed,errors}, warnings, artifacts.
6. tools/build_notebooks.py: convert every notebooks/src/*.py (percent format) to notebooks/colab/<name>.ipynb with nbformat; deterministic output (fixed metadata, no execution counts); validate each.
7. tools/pull_runs.py: git fetch origin colab-runs then git checkout origin/colab-runs -- runs/ ; clear error if branch missing.
8. tools/verify_run.py <phase> --scale <scale> [--selftest]: read docs/acceptance.yaml and runs/<scale>/<phase>/; print a table of required checks (PASS/FAIL/MISSING), global_required, soft_checks (warnings), metric bounds, suspicious_rules (evaluate the "when" expressions safely without eval; support the forms used in the yaml), presence of error.txt, last 40 lines of stdout.log; exit nonzero if any required check is not PASS, a bound is violated, or error.txt exists. --selftest runs against fixtures in tests/fixtures/runs/ covering: all PASS, a FAIL, a MISSING check, a bound violation, each suspicious rule, error.txt.
9. Notebooks (author as notebooks/src/*.py, generate ipynb): 00_setup_check (setup cell, versions, import driftsense, no_pretrained scan, splits check, bridge selftest with a temporary local bare git repo as the runs remote, record all p0 checks from acceptance.yaml, run.finish()) and 99_debug (variables SCALE, PHASE_LABEL="debug", PYTEST_ARGS; runs pytest with those args; run.finish() pushes under runs/<scale>/debug/).
10. Tests (marked p0): no_pretrained scan of src/ for the strings from_pretrained, transformers, torch.hub, anthropic, openai, chronos, timesfm (allow the strings inside tests/ only); splits boundaries and label assignment; colab_bridge using a temporary local bare git repo (mock token source) including the exception path writing error.txt; verify_run selftest cases; every notebooks/src file generates a valid notebook and regenerating produces identical JSON.
When done print: files created, and the exact Colab notebook to open.
```
Colab: open `notebooks/colab/00_setup_check.ipynb` from GitHub, Run all. Local: `python tools/pull_runs.py`.
Gemini: review `phase=p0 scale=tiny`. Tag `p0-done`.

### Prompt P1: world + infra + pricing

```
Follow AGENTS.md. Show the plan first and wait for approval. Phase P1. Execute nothing locally. Implement src/driftsense/sim/world.py, infra.py, pricing.py per docs/contracts.md and docs/traps.md.

World: hourly demand per series (provider x service) with daily, weekly, and yearly seasonality (yearly only when days >= 180), linear trend, negative-binomial noise, Indian holiday + sale + month_end calendar written to events.parquet, Poisson deployment events in working hours (Mon-Fri 10:00-18:00 local).
Infra: requests -> CPU via a capacity model (cpu = requests / (instances * capacity_per_instance)), autoscaler with scale-up and scale-down thresholds, cooldown, min and max instances (stateful per series; vectorize across resources), cumulative storage growth (monotone non-decreasing except explicit delete events), egress = requests x payload_size.
Services: compute, database, object_storage, warehouse, cdn_egress, kubernetes. Resources per service from configs/scale.yaml.
Pricing: cost = quantity x unit price by provider and region; PricingCategory On-Demand vs Committed (discount); occasional credits and refunds as negative-cost rows with ChargeCategory set; price_change events; fill ListCost >= ContractedCost >= EffectiveCost on Usage rows. Fill x_row_id (unique), x_ingest_ts (ChargePeriodEnd plus a small delay), x_source_tz = "UTC", BillingCurrency = "INR".
Provide a function build_world(cfg, scale, fault_set=None) returning the full state so faults can be applied later and the no-fault counterfactual cost computed. Seeded, deterministic, vectorized. Timestamps UTC tz-aware.

Tests (marked p1, run in Colab at SCALE=tiny): same seed gives identical output hash; storage monotone; instance count within bounds; no NaN; Usage cost = quantity x price within 1e-6; ListCost >= ContractedCost >= EffectiveCost; column set equals contracts charges columns exactly; autoscaler does not flap (instance count changes no more than once per cooldown window).

Notebook notebooks/src/01_sim_core.py (SCALE variable defaults to "small", switchable to "full"): run tests via run.run_pytest, build world+infra+pricing to Drive, plots (traffic over time, CPU vs requests, instance count, storage growth, cost by service), samples of the charges table, then record every p1 check from docs/acceptance.yaml with the exact names (seed_reproducible = two builds equal; acf_24h_peak and acf_168h_peak computed on hourly total cost; etc.), run.finish().
When done print: files created, and the exact Colab notebook to open.
```
Colab: `01_sim_core` at `SCALE="small"`. Gemini: `phase=p1 scale=small`. Tag `p1-done`.
Look at: ACF figure, instance count plot (no flapping), storage monotone.

### Prompt P2: faults + dirt + build

```
Follow AGENTS.md. Show the plan first and wait for approval. Phase P2. Execute nothing locally. Implement src/driftsense/sim/faults.py, dirt.py, build.py, configs/faults.yaml, configs/dirt.yaml per docs/contracts.md and docs/traps.md (traps 6, 7, 9, 10, 13).

Faults (inject at world/infra layer, never on the cost column; shapes step, ramp, decay):
- deployment_regression: cpu per request up (step)
- autoscaling_runaway: instance count ramp up
- traffic_surge: demand multiplier ramp then decay
- storage_leak: storage growth rate up (ramp)
- instance_upsize: unit price per instance step up, with a config_change event
- egress_spike: payload size up (step/decay), ONLY in the test split
Decoys (benign, labeled is_decoy=True): sale, month_end batch, holiday_dip.
Counts at full scale: about 6 incidents per fault type (egress_spike all in test), about 8 decoys, about 15% overlapping incidents (is_overlap=True), 3 confounded cases (a deployment event with NO real effect plus a real traffic_surge on the same day; root_cause=traffic_surge; is_confounded=True). Non-overlapping incidents on the same series are at least 3 days apart. Duration 6 to 72 hours. Scale counts down for tiny (1 per type) and small.
magnitude_inr = true extra cost: run the world with and without the fault set and sum the cost difference over [start,end).
Write ground_truth.parquet and events.parquet per contracts.

Dirt (dirt.py): first write clean_truth.parquet (identical charges before corruption), then corrupt a copy with rates from configs/dirt.yaml:
- missing_hours: drop 1-3% of resource-hours, with gap lengths drawn from {1,2,3,6,12} hours
- duplicates: 0.5% exact duplicate rows
- restatement: 1% rows get a second version with later x_ingest_ts and a changed cost
- timezone_shift: aws_like timestamps shifted by +5:30 with x_source_tz = "Asia/Kolkata"
- unit_mix: object_storage and cdn_egress rows get ConsumedUnit in GB/GiB/bytes with ConsumedQuantity converted accordingly
- null_resource_id: 0.3% rows
- cpu_glitch: 0.2% rows with x_cpu_pct up to 1000
- column_rename: azure_like rows in the later half of the monthly files use cpu_percent instead of x_cpu_pct
- tag_noise: random Tags perturbation
- currency_mix: 2% rows BillingCurrency=USD with costs converted by fx_usd_inr
Log every corruption to dirt_log.parquet. Never touch ground_truth or events. Write raw charges as one parquet per month. build.py build_dataset(scale, cfg, out_dir) runs everything with resume support.

Tests (marked p2, Colab, SCALE=tiny): every non-decoy window shows cost deviation of at least 3 robust sigma versus the no-fault world; decoys present with is_decoy=True; egress_spike absent from train and calibration; dirt_log counts within 25% of configured rates at tiny; every dirt type appears; clean_truth hash unchanged by dirt; magnitude_inr >= 0; confounded cases present with the no-effect deployment event in events.

Notebook notebooks/src/02_faults_dirt_build.py (SCALE defaults to "full"): run tests, build dataset to Drive (skip if raw/ exists unless FORCE), print counts per fault type per split, dirt counts per type, plot 4 example incidents with window shading, record all p2 checks with exact names plus metrics n_incidents_nondecoy and n_decoys, run.finish().
When done print: files created, and the exact Colab notebook to open.
```
Colab: `02_faults_dirt_build` at `SCALE="full"`. Gemini: `phase=p2 scale=full`. Tag `p2-done`.

### Prompt P3: cleaning + gold + realism gate

```
Follow AGENTS.md. Show the plan first and wait for approval. Phase P3. Execute nothing locally. Implement src/driftsense/data/clean.py, data/features.py, sim/realism.py, configs/realism.yaml, tests, and the notebook. Read docs/traps.md traps 4 to 8, 12, 14.

Cleaning (run_cleaning, Polars), steps in this exact order:
1. Read monthly raw files; harmonize schema with a rename map per file (cpu_percent -> x_cpu_pct); fix dtypes
2. Timestamps to UTC using x_source_tz
3. Units to GB (GiB x 1.073741824, bytes / 1e9)
4. Currency to INR using fx_usd_inr
5. Dedupe exact duplicates on (ChargePeriodStart, ResourceId, ChargeCategory, ServiceName, ProviderName) plus a line hash
6. Restatements: latest x_ingest_ts wins per key
7. Missing: usage gaps of 3 hours or less may be linearly interpolated and flagged; longer gaps masked and flagged; cost is NEVER imputed (cost NaN and cost_masked=True for those rows)
8. Outliers: fix physically impossible values only (x_cpu_pct above 100 is quarantined or clipped with a flag per spec in docs/contracts.md); NEVER touch cost spikes; suspicious rows go to silver/quarantine.parquet with a reason column
9. Null ResourceId rows go to quarantine with a reason (never dropped silently)
10. Validate with pandera; write silver/dq_report.md with before/after row counts per step
Credits and refunds are legitimate negative costs and must be preserved.
Scoring against clean_truth and dirt_log: recovery_rate_<dirt_type> for duplicates, timezone_shift, unit_mix, restatement, currency_mix, column_rename, cpu_glitch, missing_short_gap (fraction of corrupted rows restored to clean_truth values within a documented tolerance, or correctly quarantined where unfixable). Also verify every non-decoy ground_truth window still shows its cost deviation in silver (zero_incident_windows_lost). Cleaning must be idempotent.

Gold (build_gold): service_hour and service_day tables per contracts; cost_inr and credits_inr as defined; is_complete; split column from utils/splits.py. Features per docs/traps.md trap 8: lags >= 24h, rolling mean/std computed on data shifted by 24h, hour_of_week, calendar flags, pct change of lagged values. Auto-generate docs/data_dictionary.md and a checksum file.

Realism (sim/realism.py with thresholds in configs/realism.yaml, run on clean_truth): ACF of hourly total cost has peaks at lags 24 and 168; cost distribution heavy-tailed (report skew and kurtosis); top-3 series hold at least the configured share of cost; usage-cost correlation per service above threshold; storage monotone. Print PASS/FAIL per check with the thresholds used.

Tests (marked p3, Colab, SCALE=tiny): each cleaning step on a small hand-made frame; tests/test_leakage.py (perturb all values after time t and assert gold features at t are unchanged); credits preserved; quarantine non-empty; idempotency; masked hours never summed into cost_inr; pandera schemas for silver and gold.

Notebook notebooks/src/03_clean_gold_realism.py (SCALE defaults to "full"): Section A realism gate, Section B cleaning with before/after counts per step and recovery metrics, Section C gold tables and EDA plots (cost over time, service breakdown, usage-cost scatter, seasonality, incident overlay from ground_truth). Record all p3 checks and recovery_rate_* metrics with exact names, run.finish().
When done print: files created, and the exact Colab notebook to open.
```
Colab: `03_clean_gold_realism` at `SCALE="full"`. **Gate G1.** Gemini: `phase=p3 scale=full`. Tag `p3-done` only if realism passes and zero incident windows lost.

### Prompt P4: forecast + conformal

```
Follow AGENTS.md. Show the plan first and wait for approval. Phase P4. Execute nothing locally. Read docs/traps.md traps 1, 3, 4. Implement src/driftsense/forecast/baselines.py, gbm.py, conformal.py, tests, and the notebook.

Setup: forecast cost_inr per series at horizon 24 hours ahead. Skip incomplete hours (is_complete False) in training, calibration, and evaluation.
baselines.py: seasonal-naive with lag 168, seasonal-naive with lag 24, mean of the same hour-of-week from prior weeks.
gbm.py: LightGBM trained on the train split only; one global model with series_id as a categorical feature, or per-series models (choose one, justify in a docstring); features: lags >= 24h only, rolling mean/std on data shifted by 24h, hour_of_week, calendar flags known in advance. Never use telemetry or deployments at time t. Output forecasts per contracts.
conformal.py: split conformal on the calibration split. Score = absolute residual per series. k = ceil((n+1)*(1-alpha)); interval half-width is the k-th smallest score; infinite if k > n. alpha from configs/base.yaml (0.10). Residuals for calibration come from a model trained on the train split only. Document that coverage is marginal and approximate under time dependence.
Evaluation on the test split: MAE, RMSE, sMAPE per series (not plain MAPE); empirical coverage per series and overall vs target 0.90; mean interval width; coverage inside incident windows vs outside (evaluation code only may read ground_truth). Write p4/forecasts.parquet per contracts and p4/results.json.

Tests (marked p4, Colab, SCALE=tiny): on synthetic exchangeable data conformal coverage is near target; quantile index off-by-one test with small n; train, calibration, and test index ranges are disjoint and ordered; no NaN forecasts on complete hours; a feature-lag test asserting every feature column uses lag >= 24h.

Notebook notebooks/src/04_forecast_conformal.py (SCALE "full"): run tests, fit baselines and GBM, calibrate, evaluate, plots (forecast vs actual with band and incident overlay for 3 series, coverage table), record all p4 checks and soft check gbm_beats_snaive_mae, metrics coverage_overall, mae_gbm, mae_snaive, mean_width, run.finish().
When done print: files created, and the exact Colab notebook to open.
```
Colab: `04_forecast_conformal`. **Gate G2.** Gemini: `phase=p4 scale=full`. If GBM loses to seasonal-naive, report honestly, do not hide.

### Prompt P5: detection

```
Follow AGENTS.md. Show the plan first and wait for approval. Phase P5. Execute nothing locally. Read docs/traps.md trap 11, 10, 14. Implement src/driftsense/detect/conformal_detector.py, zscore.py, stl.py, iforest.py, eval.py, tests, and the notebook.

Detectors (all skip incomplete hours):
- conformal_detector.detect(fc, k): alarm when actual is outside [lo, hi] for k consecutive hours; merge consecutive alarmed hours into one alarm (start, end)
- zscore: forecast-residual z-score with sigma from the calibration split, same persistence rule
- stl: STL decomposition residual on the hourly series (daily period), threshold from calibration
- iforest: sklearn IsolationForest fit on train-split features, threshold on calibration
All thresholds and k tuned on the calibration split only; results reported on the test split only. Tuning functions must not receive test rows (assert it).
eval.match_events(alarms, ground_truth, tol_hours): per docs/traps.md trap 11. Metrics: event precision, recall, F1, false positives per series-day, detection delay (hours; median and p90), per-fault-type recall (egress_spike reported as its own held-out row), decoy false-alarm rate. Evaluation code is the only place ground_truth is read.
Write p5/alarms.parquet per contracts and p5/results.json.

Tests (marked p5, Colab, SCALE=tiny): hand-made matching cases (early alarm within tolerance, late alarm, double alarm for one incident, alarm on a decoy, alarm with no incident); tuning function never touches test rows; persistence rule with k=1,2,3 on a toy series.

Notebook notebooks/src/05_detection.py (SCALE "full"): run tests, run all four detectors, comparison table, per-fault recall table, decoy false alarms, detection delay, 3 example incident plots with alarm markers. Record all p5 checks and metrics event_recall, event_precision, event_f1, fp_per_series_day for the conformal detector (test split), run.finish().
When done print: files created, and the exact Colab notebook to open.
```
Colab: `05_detection`. Gemini: `phase=p5 scale=full`.

### Prompt P6: attribution + impact

```
Follow AGENTS.md. Show the plan first and wait for approval. Phase P6. Execute nothing locally. Read docs/traps.md traps 2, 9, 14. Implement src/driftsense/attribute/pvm.py, changepoint.py, control.py, drivers.py, rank.py, impact.py, baselines.py, tests, and the notebook. Attribution code must never read ground_truth; only the evaluation section of the notebook may.

- pvm.py: price-volume-mix decomposition per series for an incident window versus the pre-window baseline; exact additive: volume effect + rate effect + mix effect = total delta (test sum within 1e-6; handle one-resource series where mix is zero).
- changepoint.py: ruptures PELT on forecast residuals to localize onset inside an alarm window; penalty from config.
- control.py: ridge synthetic control. Pre-period = 14 days before onset (7 at tiny), excluding any earlier alarmed hours. Controls = series with NO alarm in the incident window (from p5 alarms). Fit ridge (scale features first) on pre-period cost of controls to predict the target series, predict the counterfactual in the window, effect = actual - counterfactual summed over complete hours, CI by block bootstrap (block 24h) of pre-period residuals. If pre-period fit error exceeds a config threshold set low_confidence=True.
- drivers.py: fit cost_inr = f(drivers) on the pre-period (ridge or small LightGBM) with drivers requests, cpu_per_request, instance_count, storage_gb, egress_per_request, unit_price. For each driver replace its window values by its pre-period same-hour-of-week mean and compute effect_k = model(actual) - model(driver_k reset), summed over the window.
- rank.py: documented rule table mapping the dominant driver to a cause: requests -> traffic_surge, cpu_per_request -> deployment_regression, instance_count -> autoscaling_runaway, storage_gb -> storage_leak, egress_per_request -> egress_spike, unit_price with a config_change event in the window -> instance_upsize. Output ranked candidates with effect_inr and score per the p6/attribution contract.
- baselines.py: correlation ranking (correlate cost residual with event indicators and driver deltas). Granger is cut.
- impact.py: overspend so far, projected month-end overspend if the effect persists, severity bucket from config, duration.
Docstrings state limits: assumes a stable pre-period relationship, unaffected controls, no unobserved confounders; an estimate, not proof of causation.

Evaluation (notebook only): only detected test incidents are attributed; undetected reported separately. Top-1 and Top-3 accuracy for counterfactual-driver and correlation, split into all, overlapping, confounded; effect_mape of effect_inr versus magnitude_inr; CI coverage of true magnitude.

Tests (marked p6, Colab, SCALE=tiny): PVM parts sum to total; synthetic control recovers a planted step effect on synthetic data within tolerance; controls never include an alarmed series; rule table covers all five root causes that attribution can name plus instance_upsize; a source scan test asserting no module under src/driftsense/attribute references ground_truth.

Notebook notebooks/src/06_attribution.py (SCALE "full"): run tests, run attribution on detected test incidents, tables for accuracy and effect error, PVM waterfall plots for three incidents, the confounded case printed explicitly with both methods. Record all p6 checks and metrics top1_counterfactual, top1_correlation, effect_mape, run.finish().
When done print: files created, and the exact Colab notebook to open.
```
Colab: `06_attribution`. Gemini: `phase=p6 scale=full`. Confounded result reported honestly even if counterfactual loses.

### Prompt P7: narrator + experiments

```
Follow AGENTS.md. Show the plan first and wait for approval. Phase P7. Execute nothing locally. Implement src/driftsense/explain/template_narrator.py, experiments/ scripts, tests, and the notebook. No LLM.

template_narrator: input evidence dict (window, series, expected, actual, PVM parts, ranked causes with effect and CI, impact, low_confidence); output a short report from fixed templates; every number in the text comes from the evidence dict; include a suggested-next-check lookup table per cause; low_confidence cases say so plainly. Test: every number in the output string appears in the evidence dict (format-aware).

experiments/ (each writes a CSV and a PNG to p7/): X1 forecast model comparison (MAE, RMSE, sMAPE); X2 conformal vs z-score (F1, FP per series-day, coverage); X3 detector comparison with per-fault recall and decoy FP rate; X4 attribution counterfactual vs correlation (Top-1, Top-3, effect error); X5 confounded-case result; X7 held-out egress_spike generalization; X8 cleaning recovery per dirt type. Run X2, X3, X4 over 3 seeds (regenerate data per seed using base seed + offset) and report mean and standard deviation. Generate docs/results_summary.md by reading the CSVs only, no hand-typed numbers; label every table "synthetic data".

Tests (marked p7, Colab, SCALE=tiny): narrator provenance; summary generator reads only CSVs (source scan for numeric literals in the generator); seeds produce different data hashes.

Notebook notebooks/src/07_narrator_experiments.py (SCALE "full"; resumes per experiment): run tests, run experiments, generate the summary, show tables. Record all p7 checks with exact names, copy a compact results_summary.md and small CSVs into the run report samples, run.finish().
When done print: files created, and the exact Colab notebook to open.
```
Colab: `07_narrator_experiments`. Long run; it resumes after a disconnect. Gemini: `phase=p7 scale=full`. Check std is not zero everywhere.

### Prompt P8: demo export

```
Follow AGENTS.md. Show the plan first and wait for approval. Phase P8. Execute nothing locally. Implement the demo export and the Plotly demo notebook. Streamlit is out of scope.

Notebook notebooks/src/08_demo_export.py (SCALE "full"): choose 5 detected test incidents (storage_leak, deployment_regression, autoscaling_runaway, traffic_surge, and one confounded case) and export to Drive demo/: series slice around the incident (pre-period plus window plus post), forecast and band, alarms, attribution results for both methods, narrator text, impact, PVM parts. Then render the demo from the exported files only (no reads from raw/silver/gold/ground_truth): overview (cost vs conformal band with alarms), per-scenario incident view (PVM waterfall, ranked causes with CI, narrator report, impact), and an hourly replay cell that steps through ticks and marks when the alarm fires and the detection delay. The confounded scenario shows correlation and counterfactual side by side. Save one PNG screenshot per scenario (under 300 KB) in figures/.
Tests (marked p8, Colab): each scenario export has all required keys; the demo section reads only files under demo/ (source scan).
Record all p8 checks with exact names, run.finish().
When done print: files created, and the exact Colab notebook to open.
```
Colab: `08_demo_export`. **Gate G3.** Gemini: `phase=p8 scale=full`.

### Prompt P9: final docs + repro

```
Follow AGENTS.md. Show the plan first and wait for approval. Phase P9. Execute nothing locally.
1. Write a script tools/make_docs.py that reads runs/full/<phase>/summary.json, artifacts metadata, and docs/results_summary.md, and generates README.md sections, docs/model_card.md, docs/dataset_card.md numbers, and docs/reproducibility.md. No hand-typed numbers.
2. README.md: problem, mermaid architecture diagram, reproduce steps (Colab notebook order 00 to 09, expected runtime per notebook from run reports), results table (copied from generated summary, labeled synthetic), limitations (synthetic data, causal assumptions, marginal and approximate conformal coverage, day-ahead design, stable pre-period assumption, attribution only for detected incidents).
3. docs/expected_summaries.json generated from the first full run reports (key_metrics and shapes).
4. Notebook notebooks/src/09_repro_check.py: verify every phase report exists on branch colab-runs, compare key metrics to docs/expected_summaries.json within tolerance, record p9 checks, run.finish().
5. Update docs/CHANGELOG.md.
When done print: files created, and the exact Colab notebook to open.
```
Colab: `09_repro_check` from a **fresh runtime** (Member 2). Gemini: `phase=p9 scale=full`. Tag `final`.

---

## PART 3. Gemini CLI prompts (use in the `gemini` session at repo root)

Review (after every Colab run):
```
@prompts/gemini/review.md phase=p3 scale=full
```
Fix (after a FAIL verdict):
```
@prompts/gemini/fix.md phase=p3 scale=full
```
Crash (when error.txt exists):
```
@prompts/gemini/triage.md phase=p3 scale=full
```
If `@file` does not work on your version, paste the file's text and add the phase and scale.

Without Gemini CLI: run `python tools/verify_run.py p3 --scale full` and paste the output plus `runs/full/p3/summary.json` into Antigravity with: "Review against docs/acceptance.yaml and docs/traps.md. Quote evidence. Do not invent numbers. If failing, follow the fix procedure in GEMINI.md."

Escalation: if the same check fails twice after Gemini fixes, stop. Open Antigravity, attach `docs/reviews/<phase>-<scale>.md` and the run report, ask for a plan-first rewrite of the affected module. Commit before switching tools.

---

## PART 4. Run sheet (7 days)

| Day | Phases | Gate |
|---|---|---|
| 1 | Part 1 setup, P0, P1 | p0 and p1 PASS |
| 2 | P2 | p2 PASS at full |
| 3 | P3 | **G1**: realism PASS, zero incident windows lost |
| 4 | P4, P5 | **G2**: coverage 0.88 to 0.92 |
| 5 | P6 | Top-1/Top-3 printed incl. confounded |
| 6 | P7, P8 | **G3**: demo from exports only |
| 7 | P9, fresh-runtime repro, slides, video | tag `final` |

Per phase: build 30-60 min, Colab 5-30 min, review 10 min.
If behind, cut in order: X6/X7 extras, multi-seed to 2, replay animation. Never cut: realism gate, cleaning scoring, coverage check, held-out fault, confounded test, leakage test.

Team (real tasks only; log in `docs/contributions.md`):
- Member 1: proofread contracts and dq/realism reports on day 3; check numbers match run reports.
- Member 2: fresh-runtime rerun and `09_repro_check` on days 6-7; spot-check Gemini reviews against raw run reports.
- Member 3: slides, demo script, video, click-through of the demo notebook on days 5-7.

## PART 5. Suspicious-result checklist

- Recall 1.0 with zero false alarms: leakage or loose tolerance.
- Coverage exactly 0.90: calibration and test overlap.
- Top-1 above 0.95: controls or drivers read ground truth.
- All recovery rates exactly 1.0: scoring compares data to itself.
- Realism PASS with thresholds not printed: check config.
- Notebook finished in seconds at full scale: stage skipped or data empty; check shapes.
- Std across seeds zero: same seed reused.
