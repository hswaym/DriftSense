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
