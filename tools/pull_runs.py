"""Pull latest Colab run reports from origin/colab-runs into local runs/."""

from pathlib import Path
import subprocess
import sys


def pull_runs() -> int:
    """Fetch and checkout the latest run reports from colab-runs branch."""
    # Check if origin remote is configured
    remote_check = subprocess.run(["git", "remote"], capture_output=True, text=True)
    if "origin" not in remote_check.stdout.split():
        print("[ERROR] Git remote 'origin' is not configured.")
        return 1

    # Check if colab-runs exists on origin
    ls_remote = subprocess.run(
        ["git", "ls-remote", "--heads", "origin", "colab-runs"],
        capture_output=True,
        text=True,
    )
    if not ls_remote.stdout.strip():
        print(
            "\n[NOTICE] Branch 'colab-runs' does not exist on remote 'origin' yet.\n"
            "Please open and execute notebook '00_setup_check.ipynb' in Google Colab first.\n"
            "The notebook's run.finish() step will automatically create 'colab-runs' and push the first run report.\n"
        )
        return 1

    # Fetch branch
    print("[INFO] Fetching branch colab-runs from origin...")
    fetch_res = subprocess.run(["git", "fetch", "origin", "colab-runs"], capture_output=True, text=True)
    if fetch_res.returncode != 0:
        print(f"[ERROR] Failed to fetch branch colab-runs: {fetch_res.stderr.strip()}")
        return 1

    # Checkout runs/ folder from origin/colab-runs
    print("[INFO] Checking out runs/ directory...")
    checkout_res = subprocess.run(
        ["git", "checkout", "origin/colab-runs", "--", "runs/"],
        capture_output=True,
        text=True,
    )
    if checkout_res.returncode != 0:
        print(f"[ERROR] Failed to checkout runs/: {checkout_res.stderr.strip()}")
        return 1

    print("[SUCCESS] Successfully pulled run reports into ./runs/")
    return 0


if __name__ == "__main__":
    sys.exit(pull_runs())
