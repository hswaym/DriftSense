# Changelog

All notable changes across project phases are logged here.

## [Phase P0] - Repository Scaffold & Setup
- Initialized repository structure (`configs/`, `src/driftsense/`, `notebooks/colab/`, `tests/`, `docs/`).
- Added strict development invariants in `AGENTS.md` (no pretrained models, time-based splits, zero data leakage).
- Authored `docs/dataset_card.md` and `docs/cleaning_spec.md`.
- Added declarative configurations (`base.yaml`, `scale.yaml`, `faults.yaml`, `dirt.yaml`, `realism.yaml`).
- Implemented `utils/seed.py`, `utils/summary.py`, and `utils/io.py`.
- Implemented `tests/test_no_pretrained.py` to enforce zero foundation / pretrained models.
- Created `notebooks/colab/00_setup_check.ipynb`.
