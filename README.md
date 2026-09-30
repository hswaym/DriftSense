# DriftSense

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

**DriftSense** is an end-to-end cloud cost anomaly detection, forecasting, and causal attribution engine built from scratch on **DriftBench-v1** (a realistic synthetic benchmark based on FinOps FOCUS standards).

---

## 🚫 Core Constraint: 100% Classical ML & From Scratch
- **Zero Pretrained Weights**: No HuggingFace `from_pretrained`, no Foundation models (Chronos, TimesFM).
- **Zero External LLMs/APIs**: Explanations and narratives generated using rule-based and template-based attribution synthesis.
- **Strict Time-Based Splits**: Zero data leakage; time $t$ uses information $\le t$ only.
- **Auditable & Transparent**: Every model, data stage, and recovery metric runs transparently in Colab notebooks with verified `RESULT SUMMARY` blocks.

---

## 📁 Repository Structure

```
driftsense/
├── AGENTS.md                  # Development rules and invariant constraints
├── README.md                  # Project overview and reproduction guide
├── requirements.txt           # Minimal dependencies
├── pyproject.toml             # Local editable package setup
├── Makefile                   # Test & lint targets
├── configs/                   # Declarative YAML configurations
│   ├── base.yaml              # Global seed, paths, time-series splits
│   ├── scale.yaml             # Data scaling configs (tiny, small, full)
│   ├── faults.yaml            # Fault injection scenarios
│   ├── dirt.yaml              # Data corruptions
│   └── realism.yaml           # Statistical realism gate criteria
├── src/driftsense/            # Core package
│   ├── sim/                   # World, infra, pricing, faults, dirt generators
│   ├── data/                  # Bronze -> Silver -> Gold cleaning & feature store
│   ├── forecast/              # Baselines, LightGBM, Conformal prediction bands
│   ├── detect/                # Z-Score, STL, Isolation Forest, Conformal detector
│   ├── attribute/             # PVM decomposition, Changepoint, Synthetic control, Drivers
│   ├── explain/               # Rule & template-based evidence narrator
│   └── utils/                 # Random seed, I/O, and summary reporters
├── notebooks/colab/           # 00..09 numbered Colab pipelines
├── tests/                     # Unit and invariant enforcement tests
└── docs/                      # Dataset card, cleaning specs, logs, and contributions
```

---

## 🚀 Quickstart

### 1. Local Setup (Tiny scale for tests)
```bash
git clone https://github.com/<your-username>/driftsense.git
cd driftsense
pip install -r requirements.txt
pip install -e .
pytest tests/
```

### 2. Colab Execution (Full scale)
Open [notebooks/colab/00_setup_check.ipynb](notebooks/colab/00_setup_check.ipynb) in Google Colab to verify runtime compatibility.
