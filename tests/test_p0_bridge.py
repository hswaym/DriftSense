"""Tests for Phase P0: Colab bridge, splits, verification, and notebook build idempotency."""

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import tempfile
import pytest

import polars as pl
import nbformat

from driftsense.utils.colab_bridge import (
    RunContext,
    _scrub_token,
    push_runs,
)
from driftsense.utils.splits import assign_split, get_split_boundaries
from tools.build_notebooks import build_all_notebooks
from tools.verify_run import run_selftest

pytestmark = pytest.mark.p0


def test_splits_boundaries_and_closed_test_interval():
    """Verify time-based splits fractions and that test interval [t2, t3] is closed."""
    t0 = datetime(2024, 1, 1, 0, 0, 0)
    t3 = datetime(2024, 1, 31, 23, 0, 0)

    b0, b1, b2, b3 = get_split_boundaries(t0, t3)
    total_sec = (t3 - t0).total_seconds()

    train_sec = (b1 - b0).total_seconds()
    calib_sec = (b2 - b1).total_seconds()

    # Fractions check
    assert abs(train_sec / total_sec - 0.667) < 1e-4
    assert abs(calib_sec / total_sec - 0.167) < 1e-4
    assert b3 == t3

    # Boundary test: check points around b1, b2, and exact last timestamp t3
    delta = timedelta(seconds=1)
    test_dts = [
        b0,               # train start
        b1 - delta,       # train end (half-open)
        b1,               # calib start
        b2 - delta,       # calib end (half-open)
        b2,               # test start
        t3,               # exact last timestamp (must be in test!)
    ]

    df = pl.DataFrame({"ChargePeriodStart": test_dts})
    labeled = assign_split(df, ts_col="ChargePeriodStart")
    labels = labeled["split"].to_list()

    assert labels[0] == "train"
    assert labels[1] == "train"
    assert labels[2] == "calib"
    assert labels[3] == "calib"
    assert labels[4] == "test"
    assert labels[5] == "test", "The exact last timestamp t3 MUST be included in the closed test interval [t2, t3]"


def test_colab_bridge_env_builder():
    """Verify run_pytest builds subprocess env with SCALE=tiny and temp artifact root."""
    run = RunContext(phase="p0", scale="full")
    with tempfile.TemporaryDirectory() as temp_dir:
        fake_art_root = Path(temp_dir) / "artifacts"
        test_env = run.build_test_env(fake_art_root)

        assert test_env["SCALE"] == "tiny", "Tests must strictly run with SCALE=tiny"
        assert test_env["DRIFTSENSE_ARTIFACT_ROOT"] == str(fake_art_root)
        assert test_env["DRIFTSENSE_ARTIFACT_ROOT"] != str(Path("./artifacts").resolve())


def test_token_scrubbing():
    """Verify secrets are completely scrubbed from messages and logs."""
    fake_token = "ghp_SECRETTOKEN1234567890abcdef"
    msg = f"Connecting with https://x-access-token:{fake_token}@github.com/repo.git failed"
    scrubbed = _scrub_token(msg, fake_token)
    assert fake_token not in scrubbed
    assert "[REDACTED" in scrubbed


def test_colab_bridge_mock_git_and_token_scrub():
    """Verify RunContext pushes to a mock bare git repo and no token leaks."""
    fake_token = "github_pat_11AAAAAA_secret9876543210"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_p = Path(temp_dir)
        bare_remote = temp_p / "remote.git"
        subprocess.run(["git", "init", "--bare", str(bare_remote)], check=True, capture_output=True)

        clone_repo = temp_p / "main_repo"
        subprocess.run(["git", "clone", str(bare_remote), str(clone_repo)], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=clone_repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=clone_repo, check=True)
        (clone_repo / "README.md").write_text("Hello")
        subprocess.run(["git", "add", "."], cwd=clone_repo, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=clone_repo, check=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=clone_repo, check=True)
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=clone_repo, check=True)

        runs_dir = clone_repo / "runs"
        worker_dir = temp_p / "runs_worker"

        # Mock token in environment
        old_env_token = os.environ.get("GITHUB_TOKEN")
        os.environ["GITHUB_TOKEN"] = fake_token
        try:
            with RunContext(phase="p0", scale="tiny", runs_dir=runs_dir) as run:
                run.check("imports_ok", True)
                run.metric("speed", 100)
                run.finish()

            push_res = push_runs(
                runs_dir=runs_dir,
                scale="tiny",
                phase="p0",
                repo_dir=clone_repo,
                runs_repo_dir=worker_dir,
            )
            assert push_res is True

            # Verify token does not appear in any written report files
            report_dir = runs_dir / "tiny" / "p0"
            for report_f in report_dir.rglob("*"):
                if report_f.is_file():
                    content = report_f.read_text(encoding="utf-8", errors="ignore")
                    assert fake_token not in content, f"Token leaked into {report_f.name}"

        finally:
            if old_env_token is not None:
                os.environ["GITHUB_TOKEN"] = old_env_token
            else:
                os.environ.pop("GITHUB_TOKEN", None)


def test_colab_bridge_push_failure_fallback():
    """Verify fallback zip is created under artifact_root/run_reports when push fails."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_p = Path(temp_dir)
        art_root = temp_p / "artifacts"
        os.environ["DRIFTSENSE_ARTIFACT_ROOT"] = str(art_root)

        fake_runs = temp_p / "runs"
        p0_dir = fake_runs / "tiny" / "p0"
        p0_dir.mkdir(parents=True, exist_ok=True)
        (p0_dir / "summary.json").write_text(json.dumps({"phase": "p0"}))

        # Push with invalid repo path triggers fallback
        invalid_repo = temp_p / "nonexistent_repo"
        pushed = push_runs(
            runs_dir=fake_runs,
            scale="tiny",
            phase="p0",
            repo_dir=invalid_repo,
        )
        assert pushed is False

        # Fallback zip must exist
        reports_dir = art_root / "run_reports"
        assert reports_dir.exists()
        zips = list(reports_dir.glob("*.zip"))
        assert len(zips) > 0, "Fallback zip was not created"


def test_verify_run_selftest_suite():
    """Verify verify_run --selftest passes all fixture scenarios."""
    ret = run_selftest()
    assert ret == 0


def test_notebooks_deterministic_build_and_validation():
    """Verify build_notebooks generates valid nbformat notebooks and is byte-identical."""
    src_dir = Path("notebooks/src")
    colab_dir = Path("notebooks/colab")

    built_1 = build_all_notebooks(src_dir, colab_dir)
    assert len(built_1) >= 4

    content_snapshot = {}
    for nb_path in built_1:
        # Validate schema
        nb = nbformat.read(nb_path, as_version=4)
        nbformat.validate(nb)
        content_snapshot[nb_path] = nb_path.read_text(encoding="utf-8")

    # Re-run compiler
    built_2 = build_all_notebooks(src_dir, colab_dir)
    for nb_path in built_2:
        new_content = nb_path.read_text(encoding="utf-8")
        assert new_content == content_snapshot[nb_path], f"Notebook {nb_path.name} output was not byte-identical on rebuild"
