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
