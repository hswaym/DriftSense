"""Verification script for Colab run reports against docs/acceptance.yaml.

Usage:
    python tools/verify_run.py <phase> --scale <scale> [--runs-dir <dir>] [--selftest]
"""

import argparse
import fnmatch
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple

# Ensure src/ is on sys.path
_src_dir = Path(__file__).resolve().parent.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

import yaml

from driftsense.utils.io import get_project_root


def safe_eval_suspicious_rule(rule_expr: str, metrics: Dict[str, Any]) -> bool:
    """Safely evaluate suspicious rule condition expressions without python eval().

    Supported forms from docs/acceptance.yaml:
    - 'key_metrics.event_recall == 1.0 and key_metrics.fp_per_series_day == 0'
    - 'key_metrics.coverage_overall == 0.9'
    - 'key_metrics.top1_counterfactual > 0.95'
    - 'all key_metrics.recovery_rate_* == 1.0'
    """
    expr = rule_expr.strip()

    # Form: all key_metrics.<pattern> == <val>
    m_all = expr.startswith("all ")
    if m_all:
        sub = expr[4:].strip()
        parts = sub.split("==")
        if len(parts) == 2:
            target_key_pat = parts[0].strip().replace("key_metrics.", "")
            target_val = float(parts[1].strip())

            matching_vals = [
                v for k, v in metrics.items()
                if fnmatch.fnmatch(k, target_key_pat) and isinstance(v, (int, float))
            ]
            if not matching_vals:
                return False
            return all(abs(v - target_val) < 1e-6 for v in matching_vals)

    # Form: clause and clause
    if " and " in expr:
        sub_clauses = expr.split(" and ")
        return all(safe_eval_suspicious_rule(c.strip(), metrics) for c in sub_clauses)

    # Single comparison clauses
    for op in ["==", "!=", ">=", "<=", ">", "<"]:
        if op in expr:
            parts = expr.split(op)
            if len(parts) == 2:
                raw_key = parts[0].strip().replace("key_metrics.", "")
                try:
                    target_val = float(parts[1].strip())
                except ValueError:
                    target_val = parts[1].strip().strip('"').strip("'")  # type: ignore

                actual_val = metrics.get(raw_key)
                if actual_val is None:
                    return False

                if op == "==":
                    return abs(float(actual_val) - float(target_val)) < 1e-6 if isinstance(target_val, float) else actual_val == target_val
                elif op == "!=":
                    return abs(float(actual_val) - float(target_val)) >= 1e-6 if isinstance(target_val, float) else actual_val != target_val
                elif op == ">":
                    return float(actual_val) > float(target_val)
                elif op == "<":
                    return float(actual_val) < float(target_val)
                elif op == ">=":
                    return float(actual_val) >= float(target_val)
                elif op == "<=":
                    return float(actual_val) <= float(target_val)

    return False


def verify_run(
    phase: str,
    scale: str,
    acceptance_path: Optional[Path] = None,
    runs_dir: Optional[Path] = None,
) -> Tuple[bool, str]:
    """Verify a run report against acceptance criteria.

    Returns (passed, report_text).
    """
    root = get_project_root()
    if acceptance_path is None:
        acceptance_path = root / "docs" / "acceptance.yaml"
    if runs_dir is None:
        runs_dir = root / "runs"

    if not acceptance_path.exists():
        return False, f"Acceptance file not found: {acceptance_path}"

    with open(acceptance_path, "r", encoding="utf-8") as f:
        acceptance = yaml.safe_load(f)

    target_dir = runs_dir / scale / phase
    if not target_dir.exists():
        return False, f"Run directory not found: {target_dir}"

    summary_file = target_dir / "summary.json"
    checks_file = target_dir / "checks.json"
    error_file = target_dir / "error.txt"
    stdout_file = target_dir / "stdout.log"

    has_error = error_file.exists()
    error_content = error_file.read_text(encoding="utf-8") if has_error else ""

    summary: Dict[str, Any] = {}
    if summary_file.exists():
        try:
            summary = json.loads(summary_file.read_text(encoding="utf-8"))
        except Exception as e:
            return False, f"Failed to parse summary.json: {e}"

    reported_checks: Dict[str, str] = {}
    if checks_file.exists():
        try:
            reported_checks = json.loads(checks_file.read_text(encoding="utf-8"))
        except Exception:
            reported_checks = summary.get("checks", {})
    else:
        reported_checks = summary.get("checks", {})

    metrics = summary.get("key_metrics", {})
    lines: List[str] = []
    lines.append(f"=== VERIFY RUN: Phase '{phase}' (Scale: {scale}) ===")
    lines.append(f"Directory: {target_dir}")
    lines.append(f"Git SHA: {summary.get('git_sha', 'unknown')}")
    lines.append(f"Runtime: {summary.get('runtime_sec', 0)}s")
    lines.append("")

    overall_pass = True

    # 1. Error check
    if has_error:
        overall_pass = False
        lines.append("[FAIL] RUN ERROR DETECTED (error.txt):")
        lines.append("--------------------------------------------------")
        lines.append(error_content.strip()[-2000:] if len(error_content) > 2000 else error_content.strip())
        lines.append("--------------------------------------------------\n")

    # 2. Global required checks
    global_req = acceptance.get("global_required", [])
    lines.append("--- Global Checks ---")
    for gc in global_req:
        res = reported_checks.get(gc, "MISSING")
        status_symbol = "[PASS]" if res == "PASS" else "[FAIL]"
        lines.append(f"  {status_symbol} {gc}: {res}")
        if res != "PASS":
            overall_pass = False

    # 3. Phase required checks
    phase_cfg = acceptance.get("phases", {}).get(phase, {})
    required_checks = phase_cfg.get("checks", [])
    soft_checks = phase_cfg.get("soft_checks", [])

    lines.append(f"\n--- Phase Checks: {phase} ---")
    for rc in required_checks:
        res = reported_checks.get(rc, "MISSING")
        status_symbol = "[PASS]" if res == "PASS" else "[FAIL]"
        lines.append(f"  {status_symbol} {rc}: {res}")
        if res != "PASS":
            overall_pass = False

    for sc in soft_checks:
        res = reported_checks.get(sc, "MISSING")
        lines.append(f"  [WARN] [Soft] {sc}: {res}")

    # 4. Metric bounds
    metric_bounds = phase_cfg.get("metrics", {})
    if metric_bounds:
        lines.append("\n--- Metric Bounds ---")
        for m_name, bounds in metric_bounds.items():
            val = metrics.get(m_name)
            if val is None:
                lines.append(f"  [FAIL] {m_name}: MISSING (expected range {bounds})")
                overall_pass = False
            else:
                try:
                    fval = float(val)
                    lo, hi = float(bounds[0]), float(bounds[1])
                    if lo <= fval <= hi:
                        lines.append(f"  [PASS] {m_name}: {fval:.4f} within [{lo}, {hi}]")
                    else:
                        lines.append(f"  [FAIL] {m_name}: {fval:.4f} VIOLATES [{lo}, {hi}]")
                        overall_pass = False
                except Exception as e:
                    lines.append(f"  [FAIL] {m_name}: Non-numeric value '{val}' ({e})")
                    overall_pass = False

    # 5. Suspicious rules
    suspicious_rules = acceptance.get("suspicious_rules", [])
    triggered_rules = []
    for s_rule in suspicious_rules:
        r_id = s_rule.get("id", "UNKNOWN")
        r_when = s_rule.get("when", "")
        if safe_eval_suspicious_rule(r_when, metrics):
            triggered_rules.append((r_id, r_when))

    if triggered_rules:
        lines.append("\n--- Suspicious Alerts Triggered ---")
        for r_id, r_when in triggered_rules:
            lines.append(f"  [ALERT] Rule {r_id}: Triggered by condition: '{r_when}'")
            overall_pass = False
    else:
        lines.append("\n--- Suspicious Rules ---")
        lines.append("  [PASS] None triggered")

    # 6. Tail stdout
    if stdout_file.exists():
        stdout_txt = stdout_file.read_text(encoding="utf-8")
        tail_lines = stdout_txt.splitlines()[-40:]
        lines.append("\n--- stdout.log (tail 40 lines) ---")
        lines.extend(tail_lines)

    lines.append("\n" + "=" * 50)
    lines.append(f"FINAL VERDICT: {'PASS' if overall_pass else 'FAIL'}")
    lines.append("=" * 50)

    report_text = "\n".join(lines)
    return overall_pass, report_text


def run_selftest() -> int:
    """Execute selftest against fixtures in tests/fixtures/runs/."""
    root = get_project_root()
    fixtures_dir = root / "tests" / "fixtures" / "runs"
    acc_path = root / "docs" / "acceptance.yaml"

    if not fixtures_dir.exists():
        print(f"[ERROR] Fixtures directory not found: {fixtures_dir}")
        return 1

    print("[INFO] Running verify_run --selftest against fixture scenarios...")
    test_cases = [
        ("all_pass", "p0", "tiny", True),
        ("fail_check", "p0", "tiny", False),
        ("missing_check", "p0", "tiny", False),
        ("bound_violation", "p2", "full", False),
        ("suspicious_s1", "p4", "full", False),
        ("suspicious_s2", "p4", "full", False),
        ("suspicious_s3", "p6", "full", False),
        ("suspicious_s4", "p3", "full", False),
        ("with_error", "p0", "tiny", False),
    ]

    all_ok = True
    for case_name, phase, scale, expected_pass in test_cases:
        case_runs_dir = fixtures_dir / case_name
        passed, report = verify_run(phase=phase, scale=scale, acceptance_path=acc_path, runs_dir=case_runs_dir)
        if passed == expected_pass:
            print(f"  [PASS] Selftest case '{case_name}': expected {expected_pass}, got {passed}")
        else:
            print(f"  [FAIL] Selftest case '{case_name}': expected {expected_pass}, got {passed}")
            print(report)
            all_ok = False

    if all_ok:
        print("\n[SUCCESS] verify_run --selftest passed all 9 test scenarios.")
        return 0
    else:
        print("\n[FAIL] verify_run --selftest failed.")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify Colab run report against docs/acceptance.yaml.")
    parser.add_argument("phase", nargs="?", default="p0", help="Phase ID (e.g. p0, p1, p2)")
    parser.add_argument("--scale", default="tiny", help="Scale (tiny, small, full)")
    parser.add_argument("--runs-dir", default=None, help="Path to runs directory")
    parser.add_argument("--acceptance", default=None, help="Path to acceptance.yaml")
    parser.add_argument("--selftest", action="store_true", help="Run selftest against fixture test cases")

    args = parser.parse_args()

    if args.selftest:
        sys.exit(run_selftest())

    r_dir = Path(args.runs_dir) if args.runs_dir else None
    a_path = Path(args.acceptance) if args.acceptance else None

    passed_verdict, output_text = verify_run(
        phase=args.phase,
        scale=args.scale,
        acceptance_path=a_path,
        runs_dir=r_dir,
    )
    print(output_text)
    sys.exit(0 if passed_verdict else 1)
