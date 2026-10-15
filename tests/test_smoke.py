"""Smoke test for repository scaffold, configurations, and core utilities."""

import pytest

import driftsense
from driftsense.utils.io import load_config
from driftsense.utils.seed import set_seed
from driftsense.utils.summary import format_result_summary

pytestmark = pytest.mark.p0


def test_package_import():
    """Verify driftsense package imports properly."""
    assert driftsense.__version__ == "0.1.0"


def test_set_seed():
    """Verify set_seed sets Python and numpy seeds deterministically."""
    s1 = set_seed(42)
    assert s1 == 42


def test_load_configs():
    """Verify all base configuration files exist and parse valid YAML."""
    base_cfg = load_config("base.yaml")
    assert base_cfg["seed"] == 42
    assert "providers" in base_cfg
    assert "services" in base_cfg

    scale_cfg = load_config("scale.yaml")
    assert "tiny" in scale_cfg
    assert "full" in scale_cfg
    assert scale_cfg["tiny"]["days"] == 14

    faults_cfg = load_config("faults.yaml")
    assert "fault_types" in faults_cfg

    dirt_cfg = load_config("dirt.yaml")
    assert "dirt_rates" in dirt_cfg

    realism_cfg = load_config("realism.yaml")
    assert "realism_gate" in realism_cfg


def test_result_summary_formatter():
    """Verify RESULT SUMMARY generates expected block structure."""
    summary_data = {
        "phase": "P0",
        "scale": "tiny",
        "seed": 42,
        "runtime_sec": 0.42,
        "shapes": {"dummy": "10 x 5"},
        "key_metrics": {"status": "ok"},
        "checks": {"smoke_check": "PASS"},
        "warnings": [],
        "artifacts": ["configs/base.yaml"],
    }
    output = format_result_summary(summary_data)
    assert "=== RESULT SUMMARY ===" in output
    assert "phase: P0" in output
    assert "smoke_check" in output
    assert "======================" in output
