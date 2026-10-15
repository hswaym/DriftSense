# DriftSense Blend Addendum

Use with `DriftSense_Prompt_Book.md` (call it the Book). This addendum **overrides the Book for Day 1 and for Book P0, P1, P2**. Book P3 to P9 stay unchanged.

State now (from the agent's own report):
- Done locally, never run in Colab: old P0 scaffold, D1 world+infra, D2 pricing, D3 faults (6 types, decoys, held-out). 17 tests pass locally (`test_d1_sim.py`, `test_d2_pricing.py`, `test_d3_faults.py`, `test_no_pretrained.py`, `test_smoke.py`).
- Existing files: `configs/dirt.yaml`, `configs/realism.yaml`, `docs/cleaning_spec.md`, `docs/dataset_card.md`, `docs/experiments.md`, `00_setup_check.ipynb`, `01_generate_data.ipynb`.
- Not built: Colab bridge, run reports, `verify_run`, acceptance file, contracts file, dirt, cleaning, everything after.

Read the agent's praise as noise ("bulletproof", "100% test coverage" are unverified). Only Colab run reports count. Local tiny passes prove little: nothing has run at full scale or on Linux/Colab yet. Expect first Colab run to expose bugs (library versions, runtime of the autoscaler loop at full, memory).

---

## 1. Name mapping (old plan vs Book)

| Old | Book | Status |
|---|---|---|
| P0 scaffold | P0 | done locally, needs bridge retrofit |
| D1 world+infra, D2 pricing | P1 | done locally, needs Colab validation |
| D3 faults | P2 (faults half) | done locally, needs Colab validation |
| D4 dirt | P2 (dirt half) | NEXT |
| D5 realism, D6 cleaning, D7 gold | P3 | pending |
| P3 forecast+conformal | P4 | pending |
| P4 detection | P5 | pending |
| P5 attribution | P6 | pending |
| P6 narrator, P7 experiments | P7 | pending |
| P8-P9 | P8, P9 | pending |

Keep existing test file names. Do not rename or rewrite working modules unless the audit says a contract gap blocks later phases.

## 2. Revised 7-day sheet

| Day | Work | Gate |
|---|---|---|
| 1 | Step A (files), R0 audit, R1 bridge retrofit, Colab runs of p0 and p1, R2 gap patches | p0, p1 PASS in Colab |
| 2 | Prompt P2b (dirt + build), Colab full build | p2 PASS at full |
| 3 | Book P3 (cleaning, gold, realism) | **G1** |
| 4 | Book P4, P5 | **G2** |
| 5 | Book P6 | attribution table incl. confounded |
| 6 | Book P7, P8 | **G3** |
| 7 | Book P9, fresh-runtime rerun, slides, video | tag `final` |

If Day 1 slips because first Colab runs fail, drop in this order: X6/X7 extras, multi-seed to 2, replay animation. Never drop: realism gate, cleaning scoring, coverage check, held-out fault, confounded test, leakage test.

---

## 3. Day 1 steps

### Step A: create the Book files by hand
From Book Part 1 create: `GEMINI.md`, `docs/contracts.md`, `docs/acceptance.yaml`, `docs/traps.md`, `prompts/gemini/review.md`, `fix.md`, `triage.md`.
`AGENTS.md` already exists: diff it against the Book version, then overwrite with the Book version (it is a superset; the Colab-only execution contract is the key change). Keep existing `docs/dataset_card.md` and `docs/cleaning_spec.md`.
Also do Book Part 1.1 items not yet done: Gemini CLI login, GitHub token as Colab Secret `GITHUB_TOKEN`. Commit and push.

### R0 prompt: audit only (read-only)
```
Follow AGENTS.md. Do not change any file except creating docs/audit_vs_contracts.md. Do not run any code. Read-only task.
Compare the existing repo (src/driftsense/*, tests/*, configs/*, notebooks/*, docs/*) against docs/contracts.md, docs/traps.md and docs/acceptance.yaml. Produce docs/audit_vs_contracts.md with one table row per difference: ID, area, what the contract says, what the code does (file and function), severity (BLOCKER for later phases / MINOR), proposed resolution (PATCH CODE or AMEND CONTRACT), estimated effort (S/M/L).
Check specifically:
1. charges columns: x_row_id, x_ingest_ts, x_source_tz, BillingCurrency present? Exact column set?
2. ground_truth columns: incident_id, start, end, series_id, root_cause, propagated_series, magnitude_inr, is_decoy, is_overlap, is_confounded. Is magnitude_inr computed from a no-fault world rerun?
3. events table schema and event types; does a confounded case exist (deployment event with no real effect plus real traffic_surge same day)?
4. series_id convention and the six services.
5. Time split: fractions 0.667/0.167/0.166 defined once in utils/splits.py, or months, or duplicated in several places?
6. Scale definitions vs configs/scale.yaml (tiny 21d, small 90d, full 365d; resources per service 1/2/4).
7. Is there a build_world(cfg, scale, fault_set=None) style function that can rerun without faults? Does egress_spike appear only in the test split?
8. Output paths vs contracts (raw/charges/<YYYY-MM>.parquet, raw/events, raw/ground_truth, raw/clean_truth).
9. Function names and signatures vs contracts section Function signatures.
10. Does any test or module write to a fixed artifacts path that would clobber real data if tests run next to a full build?
11. Does any code read ground_truth outside evaluation (traps 14)?
12. Python/library assumptions that may break on Colab (Windows paths, hardcoded separators, pinned versions).
13. Existing notebooks: contents, hand-edited ipynb, any stale outputs.
List open questions at the end. Do not propose new features.
```

### Decision rule for the audit (you, 10 minutes)
- PATCH CODE if the gap blocks dirt, cleaning, evaluation or attribution: missing `x_row_id`, `x_ingest_ts`, `x_source_tz`, `BillingCurrency`; wrong ground_truth columns; magnitude not from no-fault rerun; no confounded case; no no-fault world function; split not centralized; held-out fault leaking into train/calib.
- AMEND CONTRACT if it is naming only (file names, function names, equivalent paths) and the semantics match.
- When unsure: PATCH CODE if effort is S or M, else AMEND CONTRACT and add a note in `docs/traps.md`.
Mark each row APPLY or SKIP in the file. Member 1 can proofread this file (real task).

### R1 prompt: bridge retrofit (no changes to sim logic)
```
Follow AGENTS.md. Show the plan first and wait for approval. Execute nothing locally except ruff check, python -m compileall src, python tools/build_notebooks.py, python tools/verify_run.py --selftest. Do NOT modify the behavior of existing modules under src/driftsense/sim/. Retrofit the Colab bridge onto the existing repo.
1. Reuse existing utils (seed.py, summary.py, any splits code); extend rather than duplicate. Add or complete: utils/splits.py (time-fraction splits per docs/contracts.md; if existing split code differs, add the contract version and list callers in the plan, but do not change callers yet), utils/io.py (artifact paths from env DRIFTSENSE_ARTIFACT_ROOT, default ./artifacts), utils/colab_bridge.py (RunContext, push_runs exactly as in the Book P0 spec: require, stage, check, metric, shape, sample, figure, run_pytest, finish, error.txt on exception, size caps, token from google.colab.userdata, never log the token). IMPORTANT: run_pytest must run pytest in a subprocess with env SCALE=tiny and DRIFTSENSE_ARTIFACT_ROOT set to a fresh temp directory, so tests can never write into the real artifacts on Drive.
2. tools/build_notebooks.py, tools/pull_runs.py, tools/verify_run.py with --selftest and fixtures under tests/fixtures/runs/ (all PASS, FAIL, MISSING, bound violation, each suspicious rule, error.txt). verify_run reads docs/acceptance.yaml.
3. requirements-colab.txt (polars, duckdb, pyarrow, lightgbm, ruptures, pandera[polars], pyyaml, plotly, pytest, nbformat; no numpy/pandas/scikit-learn/scipy/matplotlib), pytest.ini with markers p0..p9 and slow, .gitignore (data/, artifacts/, runs/, __pycache__, .ipynb_checkpoints), .gitattributes (* text=auto eol=lf).
4. Add markers to existing tests without renaming files: test_smoke.py and test_no_pretrained.py -> pytestmark p0; test_d1_sim.py and test_d2_pricing.py -> p1; test_d3_faults.py -> p2. Do not change test logic.
5. Convert existing notebooks into percent-format sources under notebooks/src and regenerate ipynb: 00_setup_check (setup, versions, import driftsense, no_pretrained scan, splits check, bridge selftest with a temporary local bare git repo as the runs remote, record all p0 checks from acceptance.yaml, run.finish()); 01_sim_core (from the D1 and D2 parts of 01_generate_data: SCALE variable default "small"; run tests via run.run_pytest; build world+infra+pricing to Drive; plots of traffic, CPU vs requests, instance count, storage growth, cost by service; samples; record every p1 check with exact names from acceptance.yaml; run.finish()); 02_faults_dirt_build (faults part only for now: build faults and ground_truth, counts per type per split, example incident plots; record only checks that exist today and leave dirt checks for the next phase; SCALE default "full"); 99_debug (SCALE, PYTEST_ARGS, pushes under runs/<scale>/debug/). Keep the old ipynb files out of notebooks/colab (delete them after the new ones are generated).
6. Tests (marked p0): no_pretrained scan; splits boundaries and labels; colab_bridge with a temporary bare git repo including the exception path; verify_run selftest; every notebooks/src file builds a valid notebook and regenerating produces identical JSON.
When done print: files created, existing files changed, and the Colab notebook to open first.
```
After it finishes: `ruff check`, `python tools/build_notebooks.py`, `git push`.

### Colab validation order
1. `00_setup_check` -> `python tools/pull_runs.py` -> Gemini: `@prompts/gemini/review.md phase=p0 scale=tiny`.
2. `01_sim_core` at `SCALE="small"` -> pull -> Gemini: `phase=p1 scale=small`.
3. If time allows: `01_sim_core` at `SCALE="full"` (this is the first real test of runtime and memory; record runtime in the report).
Expect failures. Use `@prompts/gemini/fix.md` and `99_debug`. Do not move on until p0 and p1 PASS.

### R2 prompt: contract gap patches (after audit decisions)
```
Follow AGENTS.md. Show the plan first and wait for approval. Execute nothing locally except ruff check, python -m compileall src, python tools/build_notebooks.py. Read docs/audit_vs_contracts.md. Implement only the rows marked APPLY with resolution PATCH CODE; for rows marked AMEND CONTRACT, edit docs/contracts.md and say exactly what changed. For each patched row add or adjust a test (marked with the right p-marker) that runs in Colab. Do not touch rows marked SKIP. Do not change behavior beyond the patch. If a patch changes output columns or paths used by existing tests, update those tests and say so. Update notebooks/src and regenerate ipynb if checks need new names. Print a table: row ID, files changed, tests added.
```
Then rerun `01_sim_core` (small) and the faults part of `02_faults_dirt_build`; Gemini review `p1`.

---

## 4. Prompt P2b: dirt + build (Day 2) (replaces the dirt half of Book P2)

Faults already exist. Do not rewrite them.

```
Follow AGENTS.md. Show the plan first and wait for approval. Execute nothing locally except ruff check, python -m compileall src, python tools/build_notebooks.py. Phase P2b. Faults, events and ground_truth already exist; do NOT rewrite src/driftsense/sim/faults.py or world/infra/pricing except where docs/audit_vs_contracts.md rows marked APPLY say so. Read docs/traps.md (traps 5, 6, 7, 13, 14).
Implement src/driftsense/sim/dirt.py (use the existing configs/dirt.yaml; reconcile its keys with the list below and report differences) and extend src/driftsense/sim/build.py so build_dataset(scale, cfg, out_dir) runs world -> pricing -> faults -> clean_truth -> dirt with resume support, writing paths per docs/contracts.md.
Dirt: first write raw/clean_truth.parquet (identical charges before corruption), then corrupt a copy:
- missing_hours: drop 1-3% of resource-hours with gap lengths from {1,2,3,6,12} hours
- duplicates: 0.5% exact duplicate rows
- restatement: 1% rows get a second version with a later x_ingest_ts and changed cost
- timezone_shift: aws_like timestamps shifted by +5:30, x_source_tz = "Asia/Kolkata"
- unit_mix: object_storage and cdn_egress rows with ConsumedUnit in GB/GiB/bytes and ConsumedQuantity converted accordingly
- null_resource_id: 0.3% rows
- cpu_glitch: 0.2% rows with x_cpu_pct up to 1000
- column_rename: azure_like rows in the later half of the monthly files use cpu_percent instead of x_cpu_pct
- tag_noise, currency_mix (2% rows BillingCurrency=USD with costs converted by fx_usd_inr)
Log every corruption in raw/dirt_log.parquet (x_row_id, dirt_type, original_value, corrupted_value). Never touch ground_truth or events. Write raw charges as one parquet per month. Seeded and deterministic.
Tests (marked p2, Colab, SCALE=tiny): dirt_log counts within 25% of configured rates at tiny; every dirt type appears; clean_truth hash unchanged by dirt; ground_truth and events unchanged by dirt; rerun with same seed gives identical raw files; monthly files for azure_like show the renamed column only in the later half.
Update notebooks/src/02_faults_dirt_build.py (SCALE default "full"): run tests, build the full dataset to Drive (skip if raw/ exists unless FORCE), print counts per fault type per split, dirt counts per type, plot 4 example incidents with window shading, then record ALL p2 checks from docs/acceptance.yaml with exact names and metrics n_incidents_nondecoy and n_decoys, run.finish(). Regenerate the ipynb.
When done print: files created, and the Colab notebook to open.
```
Colab: `02_faults_dirt_build` at `SCALE="full"`. Pull. Gemini: `@prompts/gemini/review.md phase=p2 scale=full`. Tag `p2-done`.
Watch: egress_spike only in test; clean_truth hash stable on rerun; deviation check at full; runtime printed.

---

## 5. Then continue

Book P3 (cleaning, gold, realism) on Day 3 and onward exactly as written. One adjustment for Book P3 to P9: where a prompt names a function or module that the audit recorded under a different name, the agent must use the existing name and the contract amendment, not create a duplicate module. Add this line at the end of each Book prompt from P3:
```
Use existing module and function names recorded in docs/audit_vs_contracts.md and docs/contracts.md; do not create duplicates.
```

## 6. Team tasks for Day 1 to 2 (real, small)
- Member 1: proofread `docs/audit_vs_contracts.md`, flag unclear rows; check `dataset_card.md` still matches the code after patches.
- Member 2: after R1, open `00_setup_check` from a fresh Colab runtime and confirm the run report appears on branch `colab-runs`; log in `docs/repro_log.md`.
- Member 3: start slide skeleton and demo script from `DriftSense_Prompt_Book.md` Part 4 and the demo scenarios in P8.
Log real work in `docs/contributions.md`.

## 7. First-run risks (expect these)
- Pandera or Polars version mismatch on Colab: pin only if failing, via `requirements-colab.txt`.
- Autoscaler loop too slow at full scale: Gemini fix prompt, vectorize across resources, report runtime.
- Tests that wrote to a fixed `artifacts/` path: R1 isolates with a temp artifact root.
- Windows-only path code: audit row 12.
- Notebook finishing in seconds at full: stage skipped or empty data; check `shapes` in the run report.
