"""Helper script to generate fixtures for verify_run selftest."""

import json
from pathlib import Path


def create_fixtures():
    base = Path("tests/fixtures/runs")

    # 1. all_pass (p0, tiny)
    d = base / "all_pass" / "tiny" / "p0"
    d.mkdir(parents=True, exist_ok=True)
    p0_checks = {
        "pytest_all_green": "PASS",
        "imports_ok": "PASS",
        "versions_printed": "PASS",
        "no_pretrained_scan_clean": "PASS",
        "splits_boundaries_ok": "PASS",
        "bridge_selftest_ok": "PASS",
    }
    summary = {
        "phase": "p0",
        "scale": "tiny",
        "seed": 42,
        "runtime_sec": 1.2,
        "git_sha": "abc1234",
        "notebook": "00_setup_check",
        "shapes": {},
        "key_metrics": {},
        "checks": p0_checks,
        "pytest": {"passed": 5, "failed": 0, "errors": 0},
        "warnings": [],
        "artifacts": [],
    }
    (d / "summary.json").write_text(json.dumps(summary, indent=2))
    (d / "checks.json").write_text(json.dumps(p0_checks, indent=2))

    # 2. fail_check (p0, tiny)
    d = base / "fail_check" / "tiny" / "p0"
    d.mkdir(parents=True, exist_ok=True)
    c = dict(p0_checks)
    c["splits_boundaries_ok"] = "FAIL"
    s = dict(summary, checks=c)
    (d / "summary.json").write_text(json.dumps(s, indent=2))
    (d / "checks.json").write_text(json.dumps(c, indent=2))

    # 3. missing_check (p0, tiny)
    d = base / "missing_check" / "tiny" / "p0"
    d.mkdir(parents=True, exist_ok=True)
    c = dict(p0_checks)
    del c["imports_ok"]
    s = dict(summary, checks=c)
    (d / "summary.json").write_text(json.dumps(s, indent=2))
    (d / "checks.json").write_text(json.dumps(c, indent=2))

    # 4. bound_violation (p2, full)
    d = base / "bound_violation" / "full" / "p2"
    d.mkdir(parents=True, exist_ok=True)
    p2_checks = {
        "pytest_all_green": "PASS",
        "incident_counts_ok": "PASS",
        "deviation_3sigma_ok": "PASS",
        "decoys_present": "PASS",
        "heldout_absent_train_calib": "PASS",
        "dirt_types_all_present": "PASS",
        "dirt_rates_in_tolerance": "PASS",
        "clean_truth_hash_stable": "PASS",
        "magnitude_nonneg": "PASS",
        "confounded_cases_present": "PASS",
    }
    s = {
        "phase": "p2",
        "scale": "full",
        "seed": 42,
        "runtime_sec": 45.0,
        "git_sha": "abc1234",
        "notebook": "02_faults_dirt_build",
        "shapes": {},
        "key_metrics": {
            "n_incidents_nondecoy": 10,  # Range is [30, 60] -> violation!
            "n_decoys": 10,
        },
        "checks": p2_checks,
        "pytest": {"passed": 12, "failed": 0, "errors": 0},
        "warnings": [],
        "artifacts": [],
    }
    (d / "summary.json").write_text(json.dumps(s, indent=2))
    (d / "checks.json").write_text(json.dumps(p2_checks, indent=2))

    # 5. suspicious_s1 (p4, full)
    d = base / "suspicious_s1" / "full" / "p4"
    d.mkdir(parents=True, exist_ok=True)
    p4_checks = {
        "pytest_all_green": "PASS",
        "forecasts_no_nan_complete_hours": "PASS",
        "no_calib_in_train": "PASS",
        "splits_disjoint_ordered": "PASS",
        "coverage_within_2pts": "PASS",
    }
    s = {
        "phase": "p4",
        "scale": "full",
        "seed": 42,
        "key_metrics": {
            "coverage_overall": 0.89,
            "event_recall": 1.0,
            "fp_per_series_day": 0,  # S1 condition!
        },
        "checks": p4_checks,
    }
    (d / "summary.json").write_text(json.dumps(s, indent=2))
    (d / "checks.json").write_text(json.dumps(p4_checks, indent=2))

    # 6. suspicious_s2 (p4, full)
    d = base / "suspicious_s2" / "full" / "p4"
    d.mkdir(parents=True, exist_ok=True)
    s = {
        "phase": "p4",
        "scale": "full",
        "seed": 42,
        "key_metrics": {
            "coverage_overall": 0.9,  # S2 condition!
        },
        "checks": p4_checks,
    }
    (d / "summary.json").write_text(json.dumps(s, indent=2))
    (d / "checks.json").write_text(json.dumps(p4_checks, indent=2))

    # 7. suspicious_s3 (p6, full)
    d = base / "suspicious_s3" / "full" / "p6"
    d.mkdir(parents=True, exist_ok=True)
    p6_checks = {
        "pytest_all_green": "PASS",
        "pvm_sums_ok": "PASS",
        "controls_exclude_alarmed": "PASS",
        "rule_table_complete": "PASS",
        "overspend_nonneg": "PASS",
        "confounded_reported": "PASS",
        "low_confidence_flag_present": "PASS",
        "ground_truth_not_read_in_attribution": "PASS",
    }
    s = {
        "phase": "p6",
        "scale": "full",
        "seed": 42,
        "key_metrics": {
            "top1_counterfactual": 0.98,  # S3 condition (> 0.95)!
            "top1_correlation": 0.85,
            "effect_mape": 0.15,
        },
        "checks": p6_checks,
    }
    (d / "summary.json").write_text(json.dumps(s, indent=2))
    (d / "checks.json").write_text(json.dumps(p6_checks, indent=2))

    # 8. suspicious_s4 (p3, full)
    d = base / "suspicious_s4" / "full" / "p3"
    d.mkdir(parents=True, exist_ok=True)
    p3_checks = {
        "pytest_all_green": "PASS",
        "realism_acf_daily": "PASS",
        "realism_acf_weekly": "PASS",
        "realism_heavy_tail": "PASS",
        "realism_top3_share": "PASS",
        "realism_usage_cost_corr": "PASS",
        "realism_storage_monotone": "PASS",
        "zero_incident_windows_lost": "PASS",
        "credits_preserved": "PASS",
        "quarantine_nonempty": "PASS",
        "leakage_test_pass": "PASS",
        "silver_pandera_ok": "PASS",
        "gold_pandera_ok": "PASS",
        "cleaning_idempotent": "PASS",
    }
    s = {
        "phase": "p3",
        "scale": "full",
        "seed": 42,
        "key_metrics": {
            "recovery_rate_duplicates": 1.0,
            "recovery_rate_timezone_shift": 1.0,
            "recovery_rate_unit_mix": 1.0,
            "recovery_rate_restatement": 1.0,
            "recovery_rate_currency_mix": 1.0,
            "recovery_rate_column_rename": 1.0,
            "recovery_rate_cpu_glitch": 1.0,
            "recovery_rate_missing_short_gap": 1.0,
        },
        "checks": p3_checks,
    }
    (d / "summary.json").write_text(json.dumps(s, indent=2))
    (d / "checks.json").write_text(json.dumps(p3_checks, indent=2))

    # 9. with_error (p0, tiny)
    d = base / "with_error" / "tiny" / "p0"
    d.mkdir(parents=True, exist_ok=True)
    s = dict(summary)
    (d / "summary.json").write_text(json.dumps(s, indent=2))
    (d / "checks.json").write_text(json.dumps(p0_checks, indent=2))
    (d / "error.txt").write_text("Traceback (most recent call last):\n  File 'test.py', line 1\nZeroDivisionError: division by zero")


if __name__ == "__main__":
    create_fixtures()
    print("Fixtures created successfully.")
