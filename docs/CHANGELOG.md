# Changelog

All notable changes across project phases are logged here.

## [Phase D3] - Fault Injection & Ground Truth
- Implemented `src/driftsense/sim/faults.py`:
  - Injected 6 distinct root-cause faults at the physical telemetry layer: `deployment_regression`, `autoscaling_runaway`, `traffic_surge`, `storage_leak`, `instance_upsize`, and `egress_spike`.
  - Enforced strict held-out invariant: `egress_spike` appears solely during test split periods (months 11–12).
  - Implemented dynamic perturbation profiles: `step`, `ramp`, and `decay`.
  - Added benign decoys (`is_decoy=True`) for sales, month-end batches, and holiday dips.
  - Built confounded scenario: CI/CD deployment and traffic surge co-occurring on same date with true root cause = `traffic_surge`.
  - Generated canonical `ground_truth.parquet`.
- Implemented tests in `tests/test_d3_faults.py` verifying held-out fault absence in train/calibration, $\ge 2.5\sigma$ cost deviations, and decoy labels.
- Integrated D3 into `notebooks/colab/01_generate_data.ipynb`.

## [Phase D2] - FOCUS Pricing & Accounting Model
- Implemented `src/driftsense/sim/pricing.py`:
  - Standardized multi-provider unit pricing in INR across all 6 services.
  - Applied EDP contracted discounts (~8%) and Commitment discounts (~30%).
  - Enforced financial invariant: $ListCost \ge ContractedCost \ge EffectiveCost$.
  - Introduced legitimate negative line items for promotional credits and SLA refunds (`ChargeCategory="Credit"` / `"Refund"`, `ChargeClass="Correction"`).
  - Implemented monthly partitioned Parquet exporter (`save_partitioned_billed_parquet`).
  - Added mid-year price reduction event to discrete events log.
- Implemented tests in `tests/test_d2_pricing.py` (cost identities, credit row flags, schema completeness, and partitioned parquet reads).
- Updated `notebooks/colab/01_generate_data.ipynb` to execute and verify D1 + D2.

## [Phase D1] - World & Infrastructure Simulation
- Implemented `src/driftsense/sim/world.py`:
  - Multi-seasonality (diurnal 24h, weekly 168h, annual trend).
  - Negative-Binomial overdispersed traffic requests.
  - Indian national calendar events, sales surges, and month-end batch indicators.
  - CI/CD deployments as a Poisson process during working hours.
- Implemented `src/driftsense/sim/infra.py`:
  - Autoscaling engine with threshold hysteresis (scale-up at 72%, cooldown-protected scale-down at 35%).
  - Telemetry across 6 services (`compute`, `database`, `object_storage`, `warehouse`, `cdn_egress`, `kubernetes`) and 2 providers (`aws_like`, `azure_like`).
  - Monotonically non-decreasing cumulative storage.
- Implemented tests in `tests/test_d1_sim.py` (reproducibility, instance bounds, storage monotonicity, zero NaNs).
- Created `notebooks/colab/01_generate_data.ipynb` pipeline.

## [Phase P0] - Repository Scaffold & Setup
- Initialized repository structure (`configs/`, `src/driftsense/`, `notebooks/colab/`, `tests/`, `docs/`).
- Added strict development invariants in `AGENTS.md` (no pretrained models, time-based splits, zero data leakage).
- Authored `docs/dataset_card.md` and `docs/cleaning_spec.md`.
- Added declarative configurations (`base.yaml`, `scale.yaml`, `faults.yaml`, `dirt.yaml`, `realism.yaml`).
- Implemented `utils/seed.py`, `utils/summary.py`, and `utils/io.py`.
- Implemented `tests/test_no_pretrained.py` to enforce zero foundation / pretrained models.
- Created `notebooks/colab/00_setup_check.ipynb`.
