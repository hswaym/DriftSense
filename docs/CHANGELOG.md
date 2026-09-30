# Changelog

All notable changes across project phases are logged here.

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
