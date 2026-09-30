# DriftSense: Antigravity + Colab Project Plan

Course project (CP), data science. Solo builder + 3 support members. Due in **30 days**.

Constraints:
- Code written in **Antigravity**. Every dataset build, cleaning step, and model training runs in **Google Colab**. Notebooks show all outputs (transparency).
- **No pretrained models. No external LLM/API calls.** Every model trained from scratch on our own data.
- Dataset built from scratch (DriftBench-v1). No Kaggle.

Changes vs earlier plans:
- Chronos/TimesFM removed (pretrained).
- LLM narrator removed (pretrained). Replaced by template-based narrator.
- SHAP, FastAPI, Docker, feedback loop, MLflow, CI cut. Simple JSON/CSV logs instead.
- Scale reduced for Colab free tier and 30-day deadline.
- Learning path added (section 7): learn each concept before prompting for it.

---

## 1. Team roles

Roles are built from real, small tasks each member can actually do. Show the jury what each person really did.

| Member | Role | Real tasks |
|---|---|---|
| You | Project lead, ML and pipeline architect | Drive Antigravity, run Colab notebooks, all model code decisions, results |
| Member 1 | Data quality and documentation | Proofread dataset card + cleaning spec, review realism report, check data dictionary, verify cleaning report numbers match notebook output |
| Member 2 | Evaluation and reproducibility | Re-run each Colab notebook from a fresh runtime, confirm RESULT SUMMARY matches, run local `pytest`, log discrepancies in `docs/repro_log.md` |
| Member 3 | Presentation and demo | Build final slides, demo script, record demo video, README screenshots, rehearsal timekeeper, click-through bug testing of the dashboard |

Jury slide: "Contributions" table with the four rows above, each with 2-3 concrete items and a link to the file/commit. Keep entries true to what was done. Log real work in `docs/contributions.md` as it happens (date, person, task).

---

## 2. DO and DO NOT

### DO
- Work in phases. One phase = one Antigravity conversation. Read the plan artifact before approving.
- Learn the phase concepts first (section 7). Then prompt.
- Attach `AGENTS.md`, `docs/dataset_card.md`, and the phase spec to every prompt.
- Keep code in `src/driftsense/` as importable modules. Notebooks call the modules, show outputs, run checks.
- Seed everything from `configs/base.yaml`.
- Use time-based splits only.
- Print a `RESULT SUMMARY` block at the end of every Colab notebook. Paste it back into Antigravity to verify.
- Save all artifacts to Google Drive. Commit code only.
- Commit after each phase. Tag it (`phase-D1-done`).
- Log every real contribution in `docs/contributions.md`.

### DO NOT
- Do not use any pretrained model, `from_pretrained`, model hub weights, or LLM API. A test enforces this.
- Do not run full-scale data or training inside Antigravity. Local runs use `SCALE=tiny` for tests only.
- Do not let the agent invent metrics. Numbers come from Colab output only.
- Do not accept code you cannot explain. Ask the agent to explain, then check against section 7.
- Do not accept code without tests.
- Do not use random train/test split on time series.
- Do not delete cost spikes during cleaning. Quarantine instead.
- Do not impute cost silently.
- Do not commit data files or large artifacts. `data/` and `artifacts/` are gitignored.
- Do not change the spec silently. If spec changes, update the doc first.
- Do not claim causation from correlation. Docs state limits.

---

## 3. Workflow loop

```
Antigravity (write code + tiny tests)
      |  git push
GitHub repo
      |  git clone / git pull in Colab
Colab notebook (full scale run, training, plots, checks)
      |  save artifacts to Drive, print RESULT SUMMARY
You paste RESULT SUMMARY back to Antigravity
      |  Antigravity checks against acceptance criteria, fixes
repeat until phase checks pass -> commit + tag
```

Colab facts to respect:
- Free tier: RAM around 12 GB, sessions disconnect when idle and after long runs. Save stage outputs to Drive after every stage. Notebooks must resume from saved files.
- No GPU needed. All models are classical ML.
- Check Python and library versions in the setup cell and print them. Do not over-pin versions that conflict with Colab defaults.
- Private repo: store GitHub token in Colab Secrets. Public repo is simpler.

Demo app: Streamlit runs locally on your machine reading exported artifacts, or use a Plotly demo notebook in Colab as fallback.

---

## 4. Repo layout, config, rules

```
driftsense/
  AGENTS.md
  README.md
  requirements.txt
  configs/
    base.yaml        # seed, paths, date range
    scale.yaml       # tiny / small / full
    faults.yaml
    dirt.yaml
    realism.yaml
  src/driftsense/
    sim/             # world.py infra.py pricing.py faults.py dirt.py realism.py
    data/            # clean.py features.py schema.py
    forecast/        # baselines.py gbm.py conformal.py
    detect/          # zscore.py stl.py iforest.py conformal_detector.py eval.py
    attribute/       # pvm.py changepoint.py control.py drivers.py rank.py impact.py
    explain/         # template_narrator.py
    utils/           # seed.py io.py summary.py
  notebooks/
    colab/           # 00..09 numbered notebooks
  app/               # streamlit app
  tests/
  docs/              # dataset_card.md cleaning_spec.md experiments.md contributions.md repro_log.md figures/
  data/  artifacts/  # gitignored
```

`configs/scale.yaml`:
```
tiny:  { days: 14,  providers: 2, resources_per_provider: 6  }   # tests, local
small: { days: 90,  providers: 2, resources_per_provider: 15 }   # quick Colab check
full:  { days: 365, providers: 2, resources_per_provider: 40 }   # ~0.7M rows hourly
```

Splits at full scale: months 1-8 train, months 9-10 calibration, months 11-12 test.
Providers: `aws_like`, `azure_like`. Sim is inspired by real billing structure, not a copy of any vendor.

`AGENTS.md` (paste into Antigravity workspace rules too, if UI has that):
```
Project: DriftSense. Python. Type hints. Ruff + pytest.
Code lives in src/driftsense as importable modules. Notebooks only call modules and show outputs.
No pretrained models, no from_pretrained, no hub weights, no LLM/API calls. tests/test_no_pretrained.py enforces this.
All randomness seeded from configs/base.yaml. No hardcoded paths.
Time-based splits only. No leakage: features at time t use data up to t only.
Vectorized code (Polars, DuckDB, NumPy). No per-row Python loops on large tables.
Never delete cost spikes in cleaning. Quarantine instead. Never impute cost silently.
Local runs use SCALE=tiny. Full-scale runs happen only in Colab.
Never state metrics unless they come from provided Colab output.
Never claim causation from correlation. Document limits.
Label synthetic results as synthetic.
Explain non-obvious design choices in docstrings.
Small commits. Update docs/CHANGELOG.md each phase.
```

`requirements.txt` (loose):
```
numpy
pandas
polars
duckdb
pyarrow
scikit-learn
lightgbm
statsmodels
ruptures
scipy
matplotlib
plotly
pandera
pyyaml
streamlit
pytest
ruff
```

---

## 5. Colab notebook template

Every notebook in `notebooks/colab/` follows this cell order:

1. **Setup**: mount Drive, clone or pull repo, `pip install -r requirements.txt`, print Python + library versions, set seed.
2. **Config**: `SCALE = "full"` (switch to `"small"` for smoke run). Load configs.
3. **Run**: call module functions. Skip stage if output already on Drive (resume support).
4. **Inspect**: shapes, `head()`, key plots.
5. **Checks**: `assert` statements matching phase acceptance criteria.
6. **Save**: write artifacts to `Drive/driftsense/artifacts/<phase>/`.
7. **RESULT SUMMARY**: print block below.

RESULT SUMMARY format:
```
=== RESULT SUMMARY ===
phase: <id>
scale: <tiny|small|full>
seed: <int>
runtime_sec: <n>
shapes: {table: rows x cols, ...}
key_metrics: {name: value, ...}
checks: {check_name: PASS|FAIL, ...}
warnings: [...]
artifacts: [paths]
======================
```

Review prompt (paste into Antigravity with the summary):
```
Here is the RESULT SUMMARY from Colab for phase <id>. Compare it to the acceptance criteria in docs/plan.md for this phase. List every check that fails or looks suspicious (implausible numbers, leakage signs, too-good results). Do not invent numbers. Propose fixes as code changes with tests. Do not change the spec without telling me.
```

Notebook plan:

| Notebook | Phase |
|---|---|
| 00_setup_check | P0 |
| 01_generate_data | D1-D4 |
| 02_realism_gate | D5 |
| 03_cleaning | D6 |
| 04_gold_eda | D7 |
| 05_forecast_conformal | P3 |
| 06_detection | P4 |
| 07_attribution | P5 |
| 08_experiments | P7 |
| 09_demo_export | P8 |

---

## 6. Calendar (30 days)

| Day | Work |
|---|---|
| 1 | Learn: sections 7.1. Write dataset card + cleaning spec. P0 scaffold |
| 2 | Finish spec docs, `test_no_pretrained.py`, notebook 00 in Colab |
| 3-4 | Learn 7.2. D1 world + infra, Colab run and checks |
| 5 | D2 pricing |
| 6-7 | D3 faults, Colab run and checks |
| 8-9 | D4 dirt, Colab run and checks |
| 10 | Buffer: fix earlier phases, update docs, contribution log |
| 11 | Learn 7.3. D5 realism gate **(G1)** |
| 12-13 | D6 cleaning, recovery scoring |
| 14 | D7 gold + EDA. **Milestone M1: dataset done** |
| 15-16 | Learn 7.4. P3 baselines + LightGBM |
| 17-18 | P3 conformal, coverage check **(G2)** |
| 19-20 | Learn 7.5. P4 detectors |
| 21 | P4 evaluation, decoy analysis |
| 22-23 | Learn 7.6. P5 PVM + change-point + synthetic control |
| 24-25 | P5 driver counterfactual, rank, impact, eval vs baselines |
| 26 | P6 template narrator. P7 start |
| 27 | P7 finish, results summary |
| 28 | P8 dashboard |
| 29 | P8 demo export, click-through test **(G3)** |
| 30 | P9 report, README, demo video, final rehearsal |

Gates:
- **G1 (day 11)**: realism checks pass. No modeling before this.
- **G2 (day 18)**: conformal coverage on test within about 2 points of target.
- **G3 (day 29)**: demo runs end-to-end from exported artifacts.

If behind, apply cut order in section 11.

---

## 7. Learning path

Rule: spend 45-60 minutes on each block **before** prompting that phase. Goal: understand every module Antigravity writes well enough to explain it to the jury.

Suggested resources (verify each link opens before relying on it):
- Hyndman and Athanasopoulos, *Forecasting: Principles and Practice* (free online book)
- Angelopoulos and Bates, "A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification", arXiv:2107.07511
- Brodersen et al. 2015, "Inferring causal impact using Bayesian structural time-series models" (CausalImpact)
- Abadie, Diamond, Hainmueller, synthetic control method papers
- Truong, Oudre, Vayatis, review of change-point detection methods; `ruptures` documentation
- Liu, Ting, Zhou, "Isolation Forest" (2008)
- FinOps Foundation FOCUS specification and FinOps Framework (concepts of billed, effective, list cost)
- statsmodels, LightGBM, pandera, Polars/DuckDB official docs

### 7.1 Foundations (day 1-2): cloud cost + project framing
Learn:
- How cloud bills work: usage x unit price, on-demand vs committed, credits, billing period
- FOCUS columns: ListCost, ContractedCost, BilledCost, EffectiveCost
- What a cost anomaly is vs a legitimate change (sale, month-end batch)
- Why synthetic data with ground truth
Explain to jury: problem, why detection alone is not enough (need cause + impact), why we built the data.
Self-check:
1. Difference between BilledCost and EffectiveCost?
2. Why can a cost jump be benign?
3. Why does real billing data not give us cause labels?

### 7.2 Simulation (day 3-9): D1-D4
Learn:
- Time-series components: trend, seasonality (daily, weekly, yearly), noise
- Poisson and negative binomial counts (traffic, deployments)
- Autoscaling: threshold rule, cooldown
- Fault injection at the root layer vs at the output
- Data quality problem types and how to inject them reproducibly
Explain to jury: why faults are injected at world/infra layer, why we save `clean_truth` before adding dirt, what confounded cases test.
Self-check:
1. Why negative binomial instead of Poisson for traffic?
2. If we injected the fault directly into cost, what would break?
3. What does `dirt_log` let us measure?

### 7.3 Data quality and splits (day 11-14): D5-D7
Learn:
- Autocorrelation function (ACF), heavy tails (skew, kurtosis)
- Data leakage in time series, time-based splits, as-of joins
- Bronze/silver/gold layering
- Schema validation with pandera
Explain to jury: what the realism gate proves and does not prove, why spikes are quarantined not deleted, how leakage is tested.
Self-check:
1. What would ACF of hourly cost look like with daily seasonality?
2. Why is random train/test split wrong here?
3. Why is imputing cost dangerous but imputing short usage gaps acceptable?

### 7.4 Forecasting and conformal (day 15-18): P3
Learn:
- Baselines: seasonal-naive, exponential smoothing (Holt-Winters)
- Gradient boosting with lag and rolling features
- Expanding-window time-series cross-validation
- MAE, RMSE, MAPE and when each misleads
- Conformal prediction: exchangeability, nonconformity score, split conformal, coverage guarantee `P(Y in C(X)) >= 1 - alpha`
- Why time series only approximately satisfy exchangeability, and what rolling recalibration or adaptive conformal inference do
Explain to jury: why conformal replaces a fixed z-score threshold, what coverage means, honest limits (marginal coverage only, drift hurts).
Self-check:
1. What does 90% coverage mean and what does it not mean?
2. Why must calibration data be separate from training data?
3. What happens to coverage if the data drifts after calibration?

### 7.5 Detection (day 19-21): P4
Learn:
- Detector families: residual thresholds, STL decomposition residuals, Isolation Forest
- Event-level vs point-level evaluation
- Precision, recall, F1, false positives per day, detection delay
- Threshold tuning without touching test data
Explain to jury: why event-level matching is fairer for incidents, how decoys test false alarms.
Self-check:
1. Why is point-level F1 misleading for anomaly windows?
2. Why tune thresholds on calibration months only?
3. What does per-fault-type recall reveal that overall F1 hides?

### 7.6 Attribution (day 22-25): P5
Learn:
- Price-volume-mix (PVM) decomposition
- Change-point detection (PELT) and penalty choice
- Counterfactual thinking, synthetic control: build "what cost would have been" from unaffected series
- Driver ablation: reset one driver, measure predicted cost change
- Correlation vs causation, Granger causality and its limits, confounding
Explain to jury: how each cause gets a rupee effect with an interval, what assumptions the counterfactual needs, why the confounded test exists.
Self-check:
1. When does synthetic control fail?
2. Why can correlation rank the wrong cause on a confounded day?
3. What does the bootstrap CI capture and what does it miss?

### 7.7 Evaluation and communication (day 26-30): P6-P9
Learn:
- Experiment design: multiple seeds, mean and standard deviation, ablations
- Reporting negative results honestly
- Rule-based explanation: why every number must trace to evidence
- Dashboard storytelling
Explain to jury: what is claimed, what is not, limits of synthetic evaluation.
Self-check:
1. Which result would falsify our main claim?
2. Why report standard deviation over seeds?
3. What is the strongest criticism of this project and our answer?

---

## 8. Project phases

Common preamble for every prompt (put at top of each Antigravity conversation):
```
Follow AGENTS.md. Read docs/dataset_card.md and docs/cleaning_spec.md. Show the plan first. Write modules in src/driftsense, tiny-scale pytest tests, and the Colab notebook named below. Do not run full scale locally. Do not use any pretrained model.
```

### P0: scaffold (day 1-2)

Do first (by hand, before Antigravity): write `docs/dataset_card.md` and `docs/cleaning_spec.md` from section 9.

Prompt:
```
Create the repo scaffold from docs/plan.md section 4: folder tree, requirements.txt, configs/base.yaml, configs/scale.yaml (tiny/small/full), Makefile (test, lint), .gitignore for data/ and artifacts/, README stub, utils/seed.py, utils/summary.py (function that prints the RESULT SUMMARY block from a dict), and notebooks/colab/00_setup_check.ipynb which clones the repo, installs requirements, prints versions, runs a smoke import. Add tests/test_no_pretrained.py: scan src/ for the strings from_pretrained, transformers, torch.hub, anthropic, openai, chronos, timesfm and fail if found. Add one smoke test.
```
Checks: `pytest` passes locally. Notebook 00 runs in Colab, prints versions, `import driftsense` works.

### D1: world + infra (day 3-4)

Prompt:
```
Implement src/driftsense/sim/world.py and infra.py. World: hourly traffic with daily, weekly, yearly seasonality, trend, negative-binomial noise, Indian holiday + sale + month-end calendar, Poisson deployments in working hours. Infra: map requests to CPU via a capacity model, autoscaler with threshold and cooldown to instance count, cumulative storage growth, egress proportional to requests times payload. 6 services: compute, database, object_storage, warehouse, cdn_egress, kubernetes. Scale from configs/scale.yaml. Seeded, vectorized. Tests (tiny): reproducibility, storage monotone non-decreasing except explicit deletes, instance count within bounds, no NaN.
```
Colab: `01_generate_data` (first half). Plots: traffic over time, CPU vs requests, instance count, storage growth.
Checks: identical output on rerun with same seed; ACF peak at 24h and 168h; storage monotone; no NaN.

### D2: pricing (day 5)

Prompt:
```
Implement sim/pricing.py: cost = quantity x unit price per provider (aws_like, azure_like) and region; on-demand vs committed; credits and refunds as negative-cost rows with ChargeCategory marked; price change events. Emit FOCUS-style columns listed in docs/dataset_card.md with ListCost >= ContractedCost >= EffectiveCost. Write parquet partitioned by month. Test: cost equals quantity x price within tolerance; credits flagged; column set matches spec.
```
Checks: cost identity holds; credit rows present and flagged; column set exact.

### D3: faults (day 6-7)

Faults (6): `deployment_regression`, `autoscaling_runaway`, `traffic_surge`, `storage_leak`, `instance_upsize`, `egress_spike`. Held-out (test months only): `egress_spike`. Decoys: sale, month-end batch, holiday dip. About 8 incidents per fault type over the year, plus about 10 decoys. Overlapping faults about 15%. Confounded case: deployment and traffic surge same day, true cause traffic surge.

Prompt:
```
Implement sim/faults.py driven by configs/faults.yaml. Inject at the world or infra layer, not on the cost column, so telemetry and cost move together. Shapes: step, ramp, decay. Add benign decoys, overlapping faults (~15%) and confounded deployment+traffic cases. Write ground_truth.parquet with incident_id, start, end, service, root_cause, propagated_services, magnitude_inr, is_decoy. egress_spike appears only in the test period. Tests: every non-decoy window shows a cost deviation of at least 3 robust sigma above baseline; decoys included in ground truth with is_decoy=True; held-out fault absent from train and calibration months.
```
Checks: incident counts per type; deviation check pass; held-out rule pass.

### D4: dirt (day 8-9)

Prompt:
```
Implement sim/dirt.py. Save clean_truth.parquet first, then corrupt with rates from configs/dirt.yaml: 1-3% missing hours, 0.5% duplicates, late restated bills, timezone shift on one provider, unit mixing (GB/GiB/bytes), null ResourceId, sensor glitches (CPU up to 1000%), mid-period column rename on one provider, tag noise, currency mix. Log every corruption to dirt_log.parquet (row id, type, original value). Never corrupt ground_truth or events. Tests: dirt_log counts match configured rates within tolerance; clean_truth unchanged.
```
Colab: finish `01_generate_data`. Save `raw/`, `clean_truth`, `ground_truth`, `events`, `dirt_log` to Drive.
Checks: each corruption type appears; rates within tolerance; clean_truth hash stable.

### D5: realism gate G1 (day 11)

Prompt:
```
Create notebooks/colab/02_realism_gate.ipynb and src/driftsense/sim/realism.py. Checks from configs/realism.yaml: ACF shows daily and weekly seasonality on hourly cost; cost distribution heavy-tailed (report skew and kurtosis); top-3 services hold a large share of cost; usage vs cost near-linear per service; storage monotone. Print PASS/FAIL per check with thresholds. Optional section: if data/raw/focus_sandbox exists, compare column set and service cost share.
```
Checks: all PASS. If FAIL, tune simulator config and rerun D1-D4. **No modeling until G1 passes.**
Member 1 task: read the realism report and sign off in `docs/contributions.md`.

### D6: cleaning (day 12-13)

Cleaning order:
1. Schema harmonize, dtypes
2. Timestamps to UTC
3. Units to one standard
4. Dedupe on `(ChargePeriodStart, ResourceId, ChargeCategory, line_hash)`
5. Restatements: latest ingest wins
6. Missing: impute usage only for gaps of 3 hours or less; longer gaps masked and flagged; cost never imputed silently
7. Outliers: fix physically impossible values only (CPU above 100%); cost spikes kept; suspicious rows to quarantine
8. Validate with pandera
9. Data-quality report

Prompt:
```
Implement src/driftsense/data/clean.py as bronze->silver->gold following the 9 ordered steps in docs/cleaning_spec.md, using Polars or DuckDB. Never delete cost spikes; suspicious rows go to quarantine.parquet. Never impute cost silently; mask and flag. Validate with pandera. Score against clean_truth and dirt_log: recovery rate per corruption type, and confirm every ground_truth incident window is still visible in cleaned cost. Write data_quality_report.md. Tests on tiny data for each step.
```
Colab: `03_cleaning`. Show before/after counts per step.
Checks: recovery rate per type printed (target 90% or higher for fixable types); zero incident windows lost; credits preserved; quarantine table non-empty and explained.

### D7: gold + EDA (day 14)

Prompt:
```
Build gold service-hour and service-day tables with as-of joined event features: lags, rolling mean/std, pct change, hour of week, usage growth, CPU and request deltas, time-since-last-deployment. Add tests/test_leakage.py asserting no feature at time t uses data after t (shift-perturbation test: change future values and confirm features at t do not change). Auto-generate data dictionary and checksums. Create notebooks/colab/04_gold_eda.ipynb: cost over time, service breakdown, usage-cost correlation, seasonality, incident overlay from ground_truth.
```
Checks: leakage test passes; time splits by month applied; data dictionary generated. **Milestone M1.**

### P3: forecasting + conformal (day 15-18)

Models (all trained from scratch in Colab): seasonal-naive, Holt-Winters/ETS (statsmodels), LightGBM with lag features.

Prompt:
```
Implement src/driftsense/forecast: baselines.py (seasonal-naive, ETS via statsmodels), gbm.py (LightGBM with lag/rolling features, trained on train months only), conformal.py (split conformal on calibration months, absolute-residual score, plus rolling recalibration variant, plus optional ACI update). Evaluate with expanding-window time-series CV for tuning and report MAE, RMSE, MAPE per service on test months. Report empirical conformal coverage vs target 0.90 per service and overall, and mean interval width. Save forecasts and intervals to gold parquet. Notebook 05_forecast_conformal.ipynb with plots of forecast, band, and incidents. Log all results to artifacts/p3/results.json.
```
Checks (**G2**): test coverage within about 2 points of 0.90 overall; LightGBM beats seasonal-naive on MAE (if not, report honestly); no calibration data used in training (assert index ranges).

### P4: detection (day 19-21)

Detectors: z-score on forecast residual, moving threshold, STL residual, Isolation Forest, **conformal-band detector with persistence rule** (primary).

Prompt:
```
Implement src/driftsense/detect: zscore.py, stl.py, iforest.py, conformal_detector.py (alarm if actual is outside conformal band for k consecutive hours), eval.py for event-level matching against ground_truth (detection counts if alarm starts within the incident window or up to 6 hours before; tolerance in config). Report precision, recall, F1, false positive rate per day, detection delay, per-fault-type recall, decoy false alarms. Tune thresholds on calibration months only, report on test months only. Notebook 06_detection.ipynb with comparison table and example incident plots. Save results.json.
```
Checks: thresholds tuned without test data; table shows all detectors; decoy false alarms counted; per-type recall shows egress_spike (held-out) separately.

### P5: attribution (day 22-25)

Method (all from scratch, transparent):
1. **PVM decomposition** per service: delta cost = volume effect + rate effect + mix effect.
2. **Change-point** localization with `ruptures` (PELT) on residuals.
3. **Synthetic control** for total effect: ridge regression fit on pre-period, using other services' cost/usage as controls, predicts counterfactual cost in incident window. Effect = actual minus counterfactual, bootstrap CI from pre-period residuals.
4. **Driver counterfactual**: fit cost = f(drivers) (LightGBM or linear) on pre-period. For each driver (requests, CPU, instance count, storage, egress, unit price) and event, replace it by its expected value in the window and measure predicted cost change. Effect_k = model(actual) minus model(driver_k reset).
5. **Rank** candidate causes by effect; map drivers to fault types by a documented rule table.
6. **Baselines**: correlation ranking; Granger lag test (statsmodels).
7. **Impact**: overspend so far, projected month-end overspend, severity, duration.

Prompt:
```
Implement src/driftsense/attribute with pvm.py, changepoint.py, control.py (ridge synthetic control with bootstrap CI), drivers.py (driver ablation counterfactual), rank.py (driver-to-cause rule table, ranked output with scores), impact.py, and baselines for correlation ranking and Granger. Evaluate Top-1 and Top-3 accuracy against ground_truth on test incidents, separately for: all incidents, overlapping incidents, confounded incidents (deployment + traffic surge). Docstrings must state limits of causal claims (assumes stable pre-period relationship, no unobserved confounders). Notebook 07_attribution.ipynb with a PVM waterfall for three example incidents. Tiny-scale tests for each module.
```
Checks: Top-1 and Top-3 for three methods printed; confounded case reported explicitly (honest if counterfactual does not win); CI printed; impact numbers sane (non-negative overspend for real incidents).

### P6: template narrator (day 26, half day)

No LLM. Rule-based text from evidence.

Prompt:
```
Implement src/driftsense/explain/template_narrator.py: input incident evidence dict (window, service, expected, actual, PVM parts, ranked causes with effects and CIs, impact). Output a short report using fixed templates with every number pulled directly from the dict. Add a test that every number in the output string appears in the evidence dict. Add a suggested-next-check lookup table per cause type.
```
Checks: number-provenance test passes.

### P7: experiments (day 26-27)

Core set:

| ID | Question |
|---|---|
| X1 | Forecast model comparison (MAE/RMSE/MAPE) |
| X2 | Conformal vs z-score threshold: F1, FPR, coverage |
| X3 | Detector comparison, per-fault recall, decoy FPR |
| X4 | Attribution: counterfactual vs correlation vs Granger |
| X5 | Confounded-case test |
| X6 | Noise robustness: rerun detection at 3 noise levels |
| X7 | Held-out fault (egress_spike) generalization |
| X8 | Cleaning recovery per corruption type |

Prompt:
```
Create notebooks/colab/08_experiments.ipynb and experiments/ scripts X1-X8. Each writes a results CSV and a figure to artifacts/p7/. Run X2, X3, X4 over 5 seeds and report mean and standard deviation. Generate docs/results_summary.md by reading the CSVs only. No hand-typed numbers.
```
Checks: summary file built from CSVs; seeds varied; synthetic label on every table.

### P8: dashboard + demo (day 28-29)

Prompt:
```
Create notebooks/colab/09_demo_export.ipynb that exports to artifacts/demo/: gold parquet slices, forecasts + intervals, detected incidents, attribution results for 5 scenario incidents (one per fault type plus one confounded case). Create app/streamlit_app.py reading only those exports: Overview (cost vs conformal band, alarms), Incident page (PVM waterfall, ranked causes with effects, template narrator report, impact), Scenario replay (select a precomputed scenario, animate hourly ticks, alarm fires at detection time). Dark theme. No network calls.
```
Checks (**G3**): app starts from a clean machine using only exported artifacts; each of 5 scenarios opens and renders in a few seconds.
Member 3 task: click through every page, list bugs in `docs/repro_log.md`.

### P9: finalize (day 30)

Prompt:
```
Write README: architecture diagram (mermaid), how to reproduce (Colab notebook order), dataset card final numbers pulled from artifacts, model card, limitations section (synthetic data, causal assumptions, marginal coverage only). Add docs/reproducibility.md with exact notebook run order and expected RESULT SUMMARY values.
```
Checks: Member 2 reproduces from fresh Colab runtime and matches summaries.

---

## 9. Dataset card and cleaning spec (copy into docs/)

Dataset: DriftBench-v1, synthetic, hourly, 2 providers, 6 services, 365 days at full scale.

Columns (FOCUS-style; check exact names against the FOCUS spec if citing):
```
ChargePeriodStart, ChargePeriodEnd, BillingPeriodStart, BillingPeriodEnd,
ProviderName, SubAccountId, ServiceName, ServiceCategory, ResourceId, ResourceType,
RegionId, ChargeCategory, ChargeClass, PricingCategory,
ConsumedQuantity, ConsumedUnit, PricingQuantity,
ListCost, ContractedCost, BilledCost, EffectiveCost, Tags
x_cpu_pct, x_mem_pct, x_requests, x_storage_gb, x_egress_gb, x_instance_count
```

Side tables: `events`, `ground_truth`, `clean_truth`, `dirt_log`.

`ground_truth` columns:
```
incident_id, start, end, service, root_cause, propagated_services, magnitude_inr, is_decoy
```

Dirt injected: missing hours 1-3%, duplicates 0.5%, late restated bills, timezone shift (one provider), unit mix (GB/GiB/bytes), null ResourceId, sensor glitches, column rename (one provider), tag noise, currency mix.

Cleaning rules: see section 8 D6. Credits and refunds are legitimate negative cost.

Realism checks: daily + weekly ACF peaks, heavy-tailed cost, top-3 service share, near-linear usage-cost, monotone storage.

Real-data sanity (optional stretch): compare against a FinOps Foundation FOCUS Sandbox sample if downloaded manually.

---

## 10. Jury-facing transparency answers

- "Where is the data from?" Built from scratch. Generator code in repo, seed fixed, dataset card, realism report.
- "Why synthetic?" Real bills lack cause labels. Synthetic gives ground truth. Limits stated. Realism gate and held-out fault reduce circularity.
- "Any pretrained models?" No. Enforced by `test_no_pretrained.py`. Every model trained in a Colab notebook with visible cells.
- "Can we rerun it?" Yes. Notebook order in `docs/reproducibility.md`. Member 2 verified from fresh runtime.
- "Is attribution causal?" Counterfactual estimate under stated assumptions. Not proof of causation. Confounded-case results reported honestly.
- "What did each member do?" Show contributions table + `docs/contributions.md`.

---

## 11. Scope cuts and cut order

Already cut from original plan: pretrained forecasters, LLM narrator, SHAP, FastAPI, Docker, feedback loop, MLflow, CI, 3rd cloud provider, orphaned_resource and commitment_expiry faults, One-Class SVM, SARIMA.

If behind schedule, cut in this order:
1. Scenario replay animation (keep static incident pages)
2. Rolling recalibration and ACI variant in P3
3. Multi-seed runs for X6
4. Granger baseline (keep correlation baseline)
5. Streamlit app (fall back to Plotly notebook)
6. Yearly seasonality in simulator

Never cut: realism gate, cleaning scoring, conformal coverage check, held-out fault, confounded-case test, RESULT SUMMARY discipline.

---

## 12. Final deliverables

- GitHub repo: code, notebooks, docs, README
- Colab notebooks 00-09 running end to end
- Dataset card, data dictionary, data-quality report, realism report
- Results summary (X1-X8) from CSVs
- Model card and limitations
- Streamlit demo + 3-minute demo video
- Contributions table

Demo script (3 min):
1. Overview: cost vs conformal band, all normal
2. Pick scenario (e.g. storage leak). Alarm fires, show detection delay
3. Incident page: PVM waterfall shows where INR delta came from
4. Ranked causes with counterfactual effect and CI
5. Template narrator report
6. Impact: projected month-end overspend
7. Confounded scenario: correlation picks wrong, counterfactual result shown honestly
8. Closing slide: benchmark table + limits
