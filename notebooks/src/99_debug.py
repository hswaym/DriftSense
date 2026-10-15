# %% [markdown]
# # DriftSense: Fast Debug Runner
#
# Dedicated fast debugging notebook for executing targeted pytest arguments
# and diagnosing test failures without re-running full data generation pipelines.

# %%
import os
from pathlib import Path
import sys

# Setup path to src
current_dir = Path.cwd()
if (current_dir / "src").exists():
    sys.path.insert(0, str(current_dir / "src"))
elif (current_dir.parent / "src").exists():
    sys.path.insert(0, str(current_dir.parent / "src"))

try:
    from google.colab import drive  # type: ignore
    drive.mount("/content/drive")
    IN_COLAB = True
except Exception:
    IN_COLAB = False

from driftsense.utils.colab_bridge import RunContext

# Configure debug parameters
SCALE = "tiny"
PHASE_LABEL = "debug"
PYTEST_ARGS = ["-q", "--tb=short"]

print(f"Running Debug Suite with args: {PYTEST_ARGS}")

# %%
with RunContext(phase=PHASE_LABEL, scale=SCALE, notebook_name="99_debug") as run:
    green = run.run_pytest(PYTEST_ARGS)
    print(f"Pytest suite completed: green={green}")
    run.finish()
