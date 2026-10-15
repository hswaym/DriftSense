# %% [markdown]
# # DriftSense: Phase P0 Setup & Bridge Check
#
# Verifies Colab environment, library versions, imports, no-pretrained model invariant,
# time-fraction splits, and runs the Colab Bridge self-test.

# %%
import os
from pathlib import Path
import subprocess
import sys
import tempfile

# Setup path to src
current_dir = Path.cwd()
if (current_dir / "src").exists():
    sys.path.insert(0, str(current_dir / "src"))
elif (current_dir.parent / "src").exists():
    sys.path.insert(0, str(current_dir.parent / "src"))

print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")

# Optional Colab Drive mount
try:
    from google.colab import drive  # type: ignore
    drive.mount("/content/drive")
    IN_COLAB = True
except Exception:
    IN_COLAB = False

# Print core package versions
versions = {}
for pkg in ["polars", "duckdb", "pyarrow", "lightgbm", "ruptures", "pandera", "yaml", "plotly", "pytest", "nbformat"]:
    try:
        mod = __import__(pkg)
        versions[pkg] = getattr(mod, "__version__", "unknown")
        print(f"  {pkg}: {versions[pkg]}")
    except Exception as e:
        versions[pkg] = f"MISSING ({e})"
        print(f"  {pkg}: NOT FOUND")

# %%
import driftsense
from driftsense.utils.colab_bridge import RunContext, push_runs
from driftsense.utils.splits import assign_split, get_split_boundaries
from datetime import datetime
import polars as pl

SCALE = "tiny"
SEED = 42

with RunContext(phase="p0", scale=SCALE, seed=SEED, notebook_name="00_setup_check") as run:
    # 1. Imports check
    imports_pass = driftsense.__version__ is not None
    run.check("imports_ok", imports_pass)

    # 2. Versions printed check
    run.check("versions_printed", len(versions) >= 8)

    # 3. No-pretrained scan check
    src_dir = Path(driftsense.__file__).resolve().parent
    forbidden = ["from_pretrained", "transformers", "torch.hub", "anthropic", "openai", "chronos", "timesfm"]
    violations = []
    for py_f in src_dir.rglob("*.py"):
        content = py_f.read_text(encoding="utf-8")
        for pat in forbidden:
            if pat in content:
                violations.append(f"{py_f.name}: {pat}")
    run.check("no_pretrained_scan_clean", len(violations) == 0)

    # 4. Splits boundaries and closed interval check
    t0 = datetime(2024, 1, 1, 0, 0, 0)
    t3 = datetime(2024, 1, 22, 0, 0, 0)
    b0, b1, b2, b3 = get_split_boundaries(t0, t3)
    df_splits = pl.DataFrame({
        "ChargePeriodStart": [b0, b1, b2, b3]
    })
    labeled = assign_split(df_splits, "ChargePeriodStart")
    labels = labeled["split"].to_list()
    # Contract: [t0, t1) is train, [t1, t2) is calib, [t2, t3] is test
    splits_ok = (labels[0] == "train") and (labels[1] == "calib") and (labels[2] == "test") and (labels[3] == "test")
    run.check("splits_boundaries_ok", splits_ok)

    # 5. Bridge selftest with a local bare git repo mock remote
    with tempfile.TemporaryDirectory() as temp_dir:
        bare_remote = Path(temp_dir) / "remote_repo.git"
        subprocess.run(["git", "init", "--bare", str(bare_remote)], check=True, capture_output=True)
        clone_dir = Path(temp_dir) / "clone_repo"
        subprocess.run(["git", "clone", str(bare_remote), str(clone_dir)], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=clone_dir, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=clone_dir, check=True)
        (clone_dir / "README.md").write_text("Init")
        subprocess.run(["git", "add", "."], cwd=clone_dir, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=clone_dir, check=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=clone_dir, check=True)
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=clone_dir, check=True)

        # Test bridge push
        mock_runs = clone_dir / "runs"
        (mock_runs / "tiny" / "p0").mkdir(parents=True, exist_ok=True)
        (mock_runs / "tiny" / "p0" / "summary.json").write_text("{}")
        push_ok = push_runs(runs_dir=mock_runs, scale="tiny", phase="p0", repo_dir=clone_dir, runs_repo_dir=Path(temp_dir) / "worker")
        run.check("bridge_selftest_ok", push_ok)

    # Run p0 unit tests
    run.run_pytest(["-m", "p0"])

    run.finish()
