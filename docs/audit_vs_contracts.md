# Audit: Existing Codebase vs. Contracts

This document contains the read-only audit comparing the existing repository (`src/driftsense/*`, `tests/*`, `configs/*`, `notebooks/*`, `docs/*`) against `docs/contracts.md`, `docs/traps.md`, and `docs/acceptance.yaml`, per the R0 specification in `docs/blend_addendum.md`.

---

## 1. Audit Summary Table

| ID | Area | What the Contract Says | What the Code Does | Severity | Proposed Resolution | Effort | Decision |
|---|---|---|---|---|---|---|---|
| **A01** | `charges` schema & columns | Exact columns: `x_row_id` (int64 unique), `x_ingest_ts` (UTC), `x_source_tz` (str), `BillingCurrency`, plus standard FOCUS columns. | `src/driftsense/sim/pricing.py:FOCUS_COLUMNS` defines 28 columns, but omits `x_row_id`, `x_ingest_ts`, `x_source_tz`, and `BillingCurrency`. | **BLOCKER** | PATCH CODE | S | APPLY |
| **A02** | `ground_truth` schema | Columns: `incident_id, start, end, series_id, root_cause, propagated_series (list), magnitude_inr, is_decoy, is_overlap, is_confounded`. | `src/driftsense/sim/faults.py:GROUND_TRUTH_COLUMNS` uses `service`, `propagated_services` (string), and omits `is_overlap` and `is_confounded`. | **BLOCKER** | PATCH CODE | S | APPLY |
| **A03** | `magnitude_inr` computation | `magnitude_inr` = total extra cost over [start,end) vs. no-fault world, computed by rerunning world without fault. | `src/driftsense/sim/faults.py:inject_faults_and_decoys` computes heuristic multiplier * 1500 or hardcoded floats without no-fault rerun. | **BLOCKER** | PATCH CODE | M | APPLY |
| **A04** | `events` table schema | Schema: `ts, event_type (deployment\|config_change\|sale\|month_end\|holiday\|price_change), series_id (nullable), meta (json string)`. | `src/driftsense/sim/world.py:generate_world_timeline` uses `timestamp, event_type, service, metadata` (plain string). | **BLOCKER** | PATCH CODE | S | APPLY |
| **A05** | Confounded case event alignment | Deployment event with NO real effect plus real traffic surge on same day; true cause = `traffic_surge`. | `src/driftsense/sim/faults.py:inject_faults_and_decoys` creates the scenario but uses old schema (`service`, `metadata`) instead of `series_id` and json `meta`. | **BLOCKER** | PATCH CODE | S | APPLY |
| **A06** | `series_id` convention | `series_id = ProviderName + "/" + ServiceName` across 2 providers & 6 services (12 series total). | `sim/infra.py`, `pricing.py`, `faults.py` use separate `ProviderName` and `ServiceName`, never creating composite `series_id`. | **BLOCKER** | PATCH CODE | S | APPLY |
| **A07** | Time-based splits definition | Defined once in `utils/splits.py`: fractions 0.667 train, 0.167 calib, 0.166 test with `[t0,t1)`, `[t1,t2)`, `[t2,t3]`. | `utils/splits.py` does not exist. Splits are hardcoded dates in `configs/base.yaml` and hardcoded 60/20/20% in `faults.py`. | **BLOCKER** | PATCH CODE | S | APPLY |
| **A08** | Scale definitions in `scale.yaml` | `tiny`: 21d, 1 res/srv (6/prov); `small`: 90d, 2 res/srv (12/prov); `full`: 365d, 4 res/srv (24/prov, ~420k rows). | `configs/scale.yaml` has `tiny`: 14d, 6 res; `small`: 90d, 15 res; `full`: 365d, 40 res (~700k rows). `test_smoke.py` asserts 14d. | **BLOCKER** | PATCH CODE | S | APPLY |
| **A09** | Simulation orchestrator `sim.build` | `sim.build.build_dataset(scale: str, cfg: dict, out_dir: Path) -> dict[str, Path]` with resume support & clean baseline. | `src/driftsense/sim/build.py` does not exist. Notebook 01 manually chains simulator modules. | **BLOCKER** | PATCH CODE | M | APPLY |
| **A10** | Held-out `egress_spike` constraint | `egress_spike` appears solely in test split period. | `sim/faults.py` restricts `egress_spike` to `> cal_end_dt`, but uses legacy date threshold rather than `utils/splits.py`. | **BLOCKER** | PATCH CODE | S | APPLY |
| **A11** | Output paths & partitioning | Output under `<artifact_root>/<scale>/`: `raw/charges/<YYYY-MM>.parquet`, `raw/events.parquet`, `raw/ground_truth.parquet`, `raw/clean_truth.parquet`. | `pricing.py:save_partitioned_billed_parquet` outputs Hive partition dirs `billing_month=YYYY-MM/data.parquet` in fixed `data/raw`. | **BLOCKER** | PATCH CODE | S | APPLY |
| **A12** | Downstream function signatures | Exact signatures specified in `docs/contracts.md` for `data.clean`, `data.features`, `forecast`, `detect`, `attribute`. | Modules under `data/`, `forecast/`, `detect/`, `attribute/` are not yet created. | **MINOR** | FOLLOW CONTRACT | S | APPLY |
| **A13** | Test isolation & artifact root | Tests run with `SCALE=tiny` and `DRIFTSENSE_ARTIFACT_ROOT` in a temp dir so tests never overwrite Drive artifacts. | `tests/test_d2_pricing.py` uses tempfile, but `notebooks/colab/01_generate_data.ipynb` writes to fixed `data/raw` and `artifacts/d3`. | **MINOR** | PATCH CODE | S | APPLY |
| **A14** | `ground_truth` isolation (Trap 14) | Never read `ground_truth` in modeling, detection, or attribution code; only in evaluation code. | Compliant. Only `faults.py` writes `ground_truth`. No modeling or detection code currently touches it. | **MINOR** | AMEND CONTRACT | S | SKIP |
| **A15** | Colab dependencies | `requirements-colab.txt` containing only non-default packages (`polars`, `duckdb`, `pyarrow`, `lightgbm`, `ruptures`, `pandera[polars]`, `pyyaml`, `plotly`, `pytest`, `nbformat`). | `requirements-colab.txt` does not exist. `requirements.txt` lists heavy preinstalled libs (`numpy`, `pandas`, `scipy`, `matplotlib`, `scikit-learn`). | **BLOCKER** | PATCH CODE | S | APPLY |
| **A16** | Notebook percent format source | Notebooks authored as `notebooks/src/<name>.py` (`# %%` percent format) and built via `tools/build_notebooks.py`. Never edit `.ipynb`. | `00_setup_check.ipynb` and `01_generate_data.ipynb` exist only as hand-edited `.ipynb` JSON in `notebooks/colab/`. `notebooks/src/` is missing. | **BLOCKER** | PATCH CODE | M | APPLY |
| **A17** | Pytest markers & `pytest.ini` | Tests marked `@pytest.mark.p0..p9` and registered in `pytest.ini`. Run under 60s at `SCALE=tiny`. | `pytest.ini` is missing. Existing tests lack markers (`test_smoke`, `test_d1_sim`, etc.). | **BLOCKER** | PATCH CODE | S | APPLY |
| **A18** | Colab Bridge & Verification Tools | `src/driftsense/utils/colab_bridge.py` (`RunContext`, `push_runs`), `tools/build_notebooks.py`, `tools/pull_runs.py`, `tools/verify_run.py` with `--selftest` and fixtures. | None of these bridge utilities or verification tools exist. | **BLOCKER** | PATCH CODE | L | APPLY |

---

## 2. Detailed Audit Item Findings

### 1. charges columns
`src/driftsense/sim/pricing.py:FOCUS_COLUMNS` defines 28 columns.
- Missing contract columns: `x_row_id` (int64 unique), `x_ingest_ts` (UTC datetime), `x_source_tz` (string), `BillingCurrency` (string, default "INR").
- Impact: Blocks Phase P2b dirt injection (`dirt_log` references `x_row_id`, restatements reference `x_ingest_ts`, timezone corruption relies on `x_source_tz`, currency mixing relies on `BillingCurrency`).

### 2. ground_truth columns & magnitude
`src/driftsense/sim/faults.py:GROUND_TRUTH_COLUMNS` has:
`['incident_id', 'start', 'end', 'service', 'root_cause', 'propagated_services', 'magnitude_inr', 'is_decoy']`
- Missing contract columns: `series_id` (instead of `service`), `propagated_series` (list of strings instead of comma-delimited string), `is_overlap` (bool), `is_confounded` (bool).
- `magnitude_inr` calculation: Currently assigned via `multiplier * 1500.0` or hardcoded constants. Contract stipulates running a clean counterfactual simulation without faults and computing:
  $$\text{magnitude\_inr} = \sum_{t=\text{start}}^{\text{end}} (\text{BilledCost}_{\text{fault}} - \text{BilledCost}_{\text{clean}})$$

### 3. events table schema & confounded case
`src/driftsense/sim/world.py:generate_world_timeline` outputs:
`['timestamp', 'event_type', 'service', 'metadata']`
- Contract specifies: `ts`, `event_type`, `series_id` (nullable), `meta` (JSON string).
- Confounded case: In `src/driftsense/sim/faults.py`, a traffic surge on compute and a distracting deployment event on compute are generated for the same timestamp, satisfying the scenario requirement. However, the event record must be updated to use `series_id` and JSON `meta`.

### 4. series_id convention
`docs/contracts.md` mandates `series_id = ProviderName + "/" + ServiceName` (e.g. `aws_like/compute`, 12 unique series).
- Currently neither `infra.py` nor `pricing.py` emit `series_id`. It must be added to all telemetry/charges tables, `ground_truth`, and `events`.

### 5. Time split definition
- `src/driftsense/utils/splits.py` does not exist.
- `configs/base.yaml` specifies calendar cutoffs (`2024-08-31 23:00:00`, `2024-10-31 23:00:00`).
- `src/driftsense/sim/faults.py` uses an ad-hoc 60% / 20% / 20% rule if `days < 365`.
- Resolution: Create `src/driftsense/utils/splits.py` defining fractional split cutoffs: 0.667 train, 0.167 calib, 0.166 test, and functions `get_split_boundaries(start_dt, end_dt)` and `assign_split(df, ts_col)`.

### 6. Scale definitions
In `configs/scale.yaml`:
- Current:
  - `tiny`: 14 days, 6 resources/provider (1/service)
  - `small`: 90 days, 15 resources/provider
  - `full`: 365 days, 40 resources/provider (~0.7M rows)
- Contract:
  - `tiny`: 21 days, 1 resource per service (6 per provider, 12 total)
  - `small`: 90 days, 2 resources per service (12 per provider, 24 total)
  - `full`: 365 days, 4 resources per service (24 per provider, 48 total, ~420k raw rows)
- Note: `tests/test_smoke.py:test_load_configs` currently asserts `scale_cfg["tiny"]["days"] == 14`, which will be updated when `scale.yaml` is patched.

### 7. build_world & clean counterfactual
`src/driftsense/sim/build.py` is missing.
- Needs `build_dataset(scale: str, cfg: dict, out_dir: Path) -> dict[str, Path]` that orchestrates `world.py` -> `infra.py` -> `pricing.py` -> `faults.py` with resume support.
- Must support rerunning the pipeline without faults to obtain exact `clean_truth.parquet` and compute true `magnitude_inr`.

### 8. Output paths vs. contracts
- Contract requires:
  `<artifact_root>/<scale>/raw/charges/<YYYY-MM>.parquet`
  `<artifact_root>/<scale>/raw/events.parquet`
  `<artifact_root>/<scale>/raw/ground_truth.parquet`
  `<artifact_root>/<scale>/raw/clean_truth.parquet`
  `<artifact_root>/<scale>/raw/dirt_log.parquet`
- Code currently writes to `data/raw/billing_month=YYYY-MM/data.parquet` and `artifacts/d3/`.
- Resolution: Refactor `save_partitioned_billed_parquet` to output `<out_dir>/charges/<YYYY-MM>.parquet`.

### 9. Python/Library compatibility in Colab
- `requirements-colab.txt` is missing.
- Creating `requirements-colab.txt` with strictly non-preinstalled packages prevents runtime breakage in Colab.

### 10. Notebook generation workflow
- `notebooks/src/` does not exist.
- Raw `.ipynb` files (`00_setup_check.ipynb` and `01_generate_data.ipynb`) exist in `notebooks/colab/`.
- Per the execution contract, all notebooks must be maintained as percent-format scripts in `notebooks/src/` and compiled via `tools/build_notebooks.py`.

---

## 3. Open Questions for Lead

1. **Partition naming**: `docs/contracts.md` specifies `raw/charges/<YYYY-MM>.parquet`. Should we name the files `<YYYY-MM>.parquet` (e.g. `2024-01.parquet`) directly under `charges/` rather than nested folders? *(Recommended: Yes, per contract).*
2. **Existing `.ipynb` files**: When `tools/build_notebooks.py` generates the new `00_setup_check.ipynb`, `01_sim_core.ipynb`, `02_faults_dirt_build.ipynb`, and `99_debug.ipynb`, should the legacy `01_generate_data.ipynb` be archived or deleted? *(Recommended: Delete per Blend Addendum section 3.5).*
