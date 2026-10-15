"""Colab-to-GitHub bridge and run execution context.

This module provides RunContext and push_runs to capture verifiable run reports
(summary.json, checks.json, stdout.log, pytest.txt, error.txt, env.txt, samples/, figures/)
and push them to the repository's `colab-runs` branch.
"""

from contextlib import redirect_stdout
from datetime import datetime
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from typing import Any, Callable, Dict, List, Optional, Union
import zipfile

from driftsense.utils.io import get_artifact_root, get_project_root
from driftsense.utils.summary import print_result_summary

MAX_LOG_BYTES = 200 * 1024  # 200 KB cap for stdout.log and pytest.txt
MAX_FIGURE_BYTES = 300 * 1024  # 300 KB cap for figures


def _scrub_token(text: str, token: Optional[str] = None) -> str:
    """Scrub sensitive credentials from error logs and tracebacks."""
    if not text:
        return ""
    scrubbed = text
    if token:
        scrubbed = scrubbed.replace(token, "[REDACTED_TOKEN]")
    # Also scrub standard token formats like ghp_..., github_pat_...
    scrubbed = re.sub(r"ghp_[a-zA-Z0-9]{20,}", "[REDACTED_TOKEN]", scrubbed)
    scrubbed = re.sub(r"github_pat_[a-zA-Z0-9_]{20,}", "[REDACTED_TOKEN]", scrubbed)
    scrubbed = re.sub(r"://x-access-token:[^@]+@", "://x-access-token:[REDACTED]@ ", scrubbed)
    return scrubbed


def get_github_token() -> Optional[str]:
    """Retrieve GitHub token with lazy import of google.colab.

    Precedence:
    1. google.colab.userdata.get('GITHUB_TOKEN')
    2. os.environ.get('GITHUB_TOKEN')
    """
    token: Optional[str] = None
    try:
        from google.colab import userdata  # type: ignore # pyrefly: ignore [missing-import]
        token = userdata.get("GITHUB_TOKEN")
    except Exception:
        token = None

    if not token:
        token = os.environ.get("GITHUB_TOKEN")

    return token


def _get_git_sha(repo_dir: Path) -> str:
    """Retrieve current commit SHA."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "unknown"


def _get_remote_url(repo_dir: Path) -> Optional[str]:
    """Retrieve origin remote URL."""
    try:
        res = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return None


def push_runs(
    runs_dir: Path,
    scale: str,
    phase: str,
    repo_dir: Optional[Path] = None,
    runs_repo_dir: Optional[Path] = None,
) -> bool:
    """Push run report to branch colab-runs without leaking credentials.

    If push fails, zips report to <artifact_root>/run_reports/ as fallback.
    """
    if repo_dir is None:
        repo_dir = get_project_root()

    token = get_github_token()
    raw_remote = _get_remote_url(repo_dir)

    target_report_dir = runs_dir / scale / phase
    if not target_report_dir.exists():
        return False

    def fallback_zip(reason: str) -> None:
        try:
            art_root = get_artifact_root()
            reports_dir = art_root / "run_reports"
            reports_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            zip_path = reports_dir / f"run_report_{phase}_{scale}_{ts}.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_p in target_report_dir.rglob("*"):
                    if file_p.is_file():
                        rel = file_p.relative_to(target_report_dir)
                        zf.write(file_p, arcname=str(rel))
            print(
                f"[WARNING] Could not push run report to GitHub ({reason}). "
                f"Saved fallback zip to: {zip_path}"
            )
        except Exception as e:
            print(f"[ERROR] Failed to save fallback report zip: {e}")

    if not raw_remote:
        fallback_zip("no origin remote found")
        return False

    # Build authenticated remote in memory only
    auth_remote = raw_remote
    if token and raw_remote.startswith("https://"):
        auth_remote = re.sub(r"^https://", f"https://x-access-token:{token}@", raw_remote)

    if runs_repo_dir is None:
        if Path("/content").exists():
            runs_repo_dir = Path("/content/runs_repo")
        else:
            runs_repo_dir = Path(tempfile.gettempdir()) / "driftsense_runs_repo"

    try:
        if not runs_repo_dir.exists():
            # Attempt to clone branch colab-runs
            clone_cmd = [
                "git",
                "clone",
                "--single-branch",
                "--branch",
                "colab-runs",
                auth_remote,
                str(runs_repo_dir),
            ]
            clone_res = subprocess.run(clone_cmd, capture_output=True, text=True)
            if clone_res.returncode != 0:
                # Branch might not exist yet; initialize an orphan branch
                runs_repo_dir.mkdir(parents=True, exist_ok=True)
                subprocess.run(["git", "init"], cwd=runs_repo_dir, check=True, capture_output=True)
                subprocess.run(["git", "checkout", "--orphan", "colab-runs"], cwd=runs_repo_dir, check=True, capture_output=True)
                subprocess.run(["git", "remote", "add", "origin", auth_remote], cwd=runs_repo_dir, check=True, capture_output=True)
        else:
            # Update existing clone
            subprocess.run(["git", "remote", "set-url", "origin", auth_remote], cwd=runs_repo_dir, capture_output=True)
            subprocess.run(["git", "fetch", "origin", "colab-runs"], cwd=runs_repo_dir, capture_output=True)
            subprocess.run(["git", "checkout", "colab-runs"], cwd=runs_repo_dir, capture_output=True)
            subprocess.run(["git", "pull", "--rebase", "origin", "colab-runs"], cwd=runs_repo_dir, capture_output=True)

        # Copy report directory into runs/<scale>/<phase>
        dest_report_dir = runs_repo_dir / "runs" / scale / phase
        if dest_report_dir.exists():
            shutil.rmtree(dest_report_dir)
        dest_report_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(target_report_dir, dest_report_dir)

        # Commit and push
        subprocess.run(["git", "config", "user.name", "DriftSense Colab Bridge"], cwd=runs_repo_dir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "bridge@driftsense.local"], cwd=runs_repo_dir, capture_output=True)
        subprocess.run(["git", "add", "runs/"], cwd=runs_repo_dir, check=True, capture_output=True)

        status_res = subprocess.run(["git", "status", "--porcelain"], cwd=runs_repo_dir, capture_output=True, text=True)
        if not status_res.stdout.strip():
            print(f"[INFO] Run report for {phase} ({scale}) is up-to-date on branch colab-runs.")
            return True

        commit_msg = f"report({phase}): run report at scale={scale} [{datetime.utcnow().isoformat()}]"
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=runs_repo_dir, check=True, capture_output=True)

        # Push with single rebase retry on conflict
        push_res = subprocess.run(["git", "push", "-u", "origin", "colab-runs"], cwd=runs_repo_dir, capture_output=True, text=True)
        if push_res.returncode != 0:
            # Retry with pull --rebase
            subprocess.run(["git", "pull", "--rebase", "origin", "colab-runs"], cwd=runs_repo_dir, capture_output=True)
            push_res = subprocess.run(["git", "push", "-u", "origin", "colab-runs"], cwd=runs_repo_dir, capture_output=True, text=True)

        if push_res.returncode == 0:
            print(f"[INFO] Successfully pushed run report for {phase} ({scale}) to colab-runs.")
            return True
        else:
            err_msg = _scrub_token(push_res.stderr, token)
            fallback_zip(f"git push error: {err_msg}")
            return False

    except Exception as e:
        err_msg = _scrub_token(str(e), token)
        fallback_zip(err_msg)
        return False


class RunContext:
    """Execution context manager for a single notebook phase."""

    def __init__(
        self,
        phase: str,
        scale: str = "tiny",
        seed: int = 42,
        notebook_name: Optional[str] = None,
        runs_dir: Optional[Path] = None,
    ):
        self.phase = phase
        self.scale = scale
        self.seed = seed
        self.notebook_name = notebook_name or f"{phase}_run"
        self.repo_dir = get_project_root()
        self.runs_dir = runs_dir or (self.repo_dir / "runs")
        self.phase_dir = self.runs_dir / self.scale / self.phase

        self.start_time: float = 0.0
        self.runtime_sec: float = 0.0
        self.git_sha: str = "unknown"

        self.shapes: Dict[str, Union[List[int], str]] = {}
        self.key_metrics: Dict[str, Union[float, int, str]] = {}
        self.checks: Dict[str, str] = {}
        self.warnings: List[str] = []
        self.artifacts: List[str] = []
        self.pytest_counts: Dict[str, int] = {"passed": 0, "failed": 0, "errors": 0}

        self._stdout_buffer = io.StringIO()
        self._captured_prints: List[str] = []

    def __enter__(self) -> "RunContext":
        import time

        self.start_time = time.time()
        self.git_sha = _get_git_sha(self.repo_dir)
        self.phase_dir.mkdir(parents=True, exist_ok=True)
        (self.phase_dir / "samples").mkdir(parents=True, exist_ok=True)
        (self.phase_dir / "figures").mkdir(parents=True, exist_ok=True)

        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> bool:
        import time

        self.runtime_sec = round(time.time() - self.start_time, 2)

        if exc_type is not None:
            token = get_github_token()
            tb_str = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
            scrubbed_tb = _scrub_token(tb_str, token)
            error_file = self.phase_dir / "error.txt"
            error_file.write_text(scrubbed_tb, encoding="utf-8")
            self.warnings.append(f"Run crashed: {_scrub_token(str(exc_val), token)}")

            # Still write artifacts and summary before re-raising
            self._write_reports()
            push_runs(self.runs_dir, self.scale, self.phase, self.repo_dir)
            return False  # Re-raise exception

        return False

    def require(self, paths: List[Union[str, Path]]) -> None:
        """Verify required input paths exist before proceeding."""
        missing = []
        for p in paths:
            path_obj = Path(p)
            if not path_obj.exists():
                missing.append(str(path_obj))
        if missing:
            raise RuntimeError(
                f"Required input artifact(s) missing: {missing}. Run prior pipeline phases first."
            )

    def stage(
        self,
        name: str,
        fn: Callable[[], Any],
        out_path: Optional[Union[str, Path]] = None,
        force: bool = False,
    ) -> Any:
        """Execute stage function with resume support."""
        if out_path is not None and not force:
            p = Path(out_path)
            if p.exists():
                print(f"[STAGE: {name}] Output already exists at {p}. Skipping (resume enabled).")
                return None

        print(f"[STAGE: {name}] Running...")
        result = fn()
        if out_path:
            self.artifacts.append(str(out_path))
        return result

    def check(self, name: str, passed: bool) -> None:
        """Record check result PASS/FAIL."""
        self.checks[name] = "PASS" if passed else "FAIL"

    def metric(self, name: str, value: Union[float, int, str]) -> None:
        """Record key metric."""
        self.key_metrics[name] = value

    def shape(self, name: str, df: Any) -> None:
        """Record DataFrame shape."""
        if hasattr(df, "shape"):
            self.shapes[name] = list(df.shape)
        elif hasattr(df, "height") and hasattr(df, "width"):
            self.shapes[name] = [df.height, df.width]
        else:
            self.shapes[name] = str(type(df))

    def sample(self, name: str, df: Any, n: int = 20) -> Path:
        """Export head(n) sample to CSV."""
        sample_path = self.phase_dir / "samples" / f"{name}.csv"
        if hasattr(df, "head"):
            head_df = df.head(n)
            if hasattr(head_df, "write_csv"):
                head_df.write_csv(sample_path)
            elif hasattr(head_df, "to_csv"):
                head_df.to_csv(sample_path, index=False)
        return sample_path

    def figure(self, name: str, fig: Any) -> Path:
        """Save plot figure enforcing 300 KB ceiling."""
        fig_path = self.phase_dir / "figures" / f"{name}.png"
        if hasattr(fig, "write_image"):
            # Plotly
            fig.write_image(str(fig_path), scale=1)
        elif hasattr(fig, "savefig"):
            # Matplotlib
            fig.savefig(fig_path, dpi=100, bbox_inches="tight")

        # Enforce size limit
        if fig_path.exists() and fig_path.stat().st_size > MAX_FIGURE_BYTES:
            if hasattr(fig, "savefig"):
                fig.savefig(fig_path, dpi=70, bbox_inches="tight")
        return fig_path

    def build_test_env(self, temp_artifact_dir: Path) -> Dict[str, str]:
        """Build isolated subprocess environment for running tests."""
        test_env = os.environ.copy()
        test_env["SCALE"] = "tiny"
        test_env["DRIFTSENSE_ARTIFACT_ROOT"] = str(temp_artifact_dir)
        return test_env

    def run_pytest(self, args: Optional[List[str]] = None) -> bool:
        """Execute pytest in isolated subprocess without writing to Drive artifacts."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_art = Path(temp_dir) / "artifacts"
            temp_art.mkdir(parents=True, exist_ok=True)
            test_env = self.build_test_env(temp_art)

            cmd = [sys.executable, "-m", "pytest", "-q", "--tb=short"]
            if args:
                cmd.extend(args)

            try:
                res = subprocess.run(
                    cmd,
                    cwd=self.repo_dir,
                    env=test_env,
                    capture_output=True,
                    text=True,
                )
                output = res.stdout + "\n" + res.stderr
            except Exception as e:
                output = f"Failed to execute pytest: {e}"
                res = subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr=output)

        # Cap output at 200 KB
        pytest_txt_content = output[-MAX_LOG_BYTES:] if len(output) > MAX_LOG_BYTES else output
        pytest_file = self.phase_dir / "pytest.txt"
        pytest_file.write_text(pytest_txt_content, encoding="utf-8")

        # Parse counts
        passed_m = re.search(r"(\d+)\s+passed", output)
        failed_m = re.search(r"(\d+)\s+failed", output)
        errors_m = re.search(r"(\d+)\s+error", output)

        n_passed = int(passed_m.group(1)) if passed_m else 0
        n_failed = int(failed_m.group(1)) if failed_m else 0
        n_errors = int(errors_m.group(1)) if errors_m else 0

        self.pytest_counts = {"passed": n_passed, "failed": n_failed, "errors": n_errors}
        is_green = (res.returncode == 0) and (n_failed == 0) and (n_errors == 0) and (n_passed > 0)
        self.check("pytest_all_green", is_green)
        return is_green

    def _write_reports(self) -> None:
        """Write summary.json, checks.json, stdout.log, and env.txt."""
        summary = {
            "phase": self.phase,
            "scale": self.scale,
            "seed": self.seed,
            "runtime_sec": self.runtime_sec,
            "git_sha": self.git_sha,
            "notebook": self.notebook_name,
            "shapes": self.shapes,
            "key_metrics": self.key_metrics,
            "checks": self.checks,
            "pytest": self.pytest_counts,
            "warnings": self.warnings,
            "artifacts": self.artifacts,
        }

        # summary.json
        summary_file = self.phase_dir / "summary.json"
        summary_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        # checks.json
        checks_file = self.phase_dir / "checks.json"
        checks_file.write_text(json.dumps(self.checks, indent=2), encoding="utf-8")

        # env.txt
        env_lines = [
            f"Python: {sys.version}",
            f"Git SHA: {self.git_sha}",
            f"Phase: {self.phase}",
            f"Scale: {self.scale}",
            f"Timestamp: {datetime.utcnow().isoformat()}",
        ]
        for pkg in ["polars", "duckdb", "pyarrow", "lightgbm", "ruptures", "pandera", "yaml", "plotly", "pytest", "nbformat"]:
            try:
                mod = __import__(pkg)
                env_lines.append(f"{pkg}: {getattr(mod, '__version__', 'unknown')}")
            except Exception:
                pass

        (self.phase_dir / "env.txt").write_text("\n".join(env_lines), encoding="utf-8")

        # stdout.log (tail 200 KB)
        token = get_github_token()
        captured_text = _scrub_token(self._stdout_buffer.getvalue(), token)
        stdout_tail = captured_text[-MAX_LOG_BYTES:] if len(captured_text) > MAX_LOG_BYTES else captured_text
        (self.phase_dir / "stdout.log").write_text(stdout_tail, encoding="utf-8")

    def finish(self) -> None:
        """Finalize run report, print RESULT SUMMARY, and push to branch colab-runs."""
        import time

        self.runtime_sec = round(time.time() - self.start_time, 2)
        self._write_reports()

        summary_data = {
            "phase": self.phase,
            "scale": self.scale,
            "seed": self.seed,
            "runtime_sec": self.runtime_sec,
            "shapes": {k: f"{v[0]} x {v[1]}" if isinstance(v, list) and len(v) == 2 else str(v) for k, v in self.shapes.items()},
            "key_metrics": self.key_metrics,
            "checks": self.checks,
            "warnings": self.warnings,
            "artifacts": self.artifacts,
        }
        print_result_summary(summary_data)
        push_runs(self.runs_dir, self.scale, self.phase, self.repo_dir)
