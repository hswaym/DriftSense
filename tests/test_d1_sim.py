"""Tests for Phase D1: World and Infrastructure Simulation."""

import numpy as np
import polars as pl
import pytest

from driftsense.sim.infra import generate_infra_telemetry
from driftsense.sim.world import generate_world_timeline
from driftsense.utils.io import load_config


@pytest.fixture
def scale_cfg():
    return load_config("scale.yaml")


def test_world_timeline_reproducibility(scale_cfg):
    """Verify that world generation with the same seed produces identical results."""
    days = scale_cfg["tiny"]["days"]
    w1, e1 = generate_world_timeline(days=days, seed=42)
    w2, e2 = generate_world_timeline(days=days, seed=42)

    assert w1.equals(w2)
    assert e1.equals(e2)


def test_world_timeline_properties(scale_cfg):
    """Verify world timeline contains no NaNs, correct row counts, and positive requests."""
    days = scale_cfg["tiny"]["days"]
    w, e = generate_world_timeline(days=days, seed=42)

    assert len(w) == days * 24
    assert w["traffic_requests"].null_count() == 0
    assert (w["traffic_requests"] > 0).all()
    assert (w["deployments"] >= 0).all()
    # Deployments should only occur during work hours
    work_hour_deps = w.filter(
        (pl.col("day_of_week") >= 5) | (pl.col("hour_of_day") < 10) | (pl.col("hour_of_day") >= 18)
    )
    assert work_hour_deps["deployments"].sum() == 0


def test_infra_telemetry_properties(scale_cfg):
    """Verify infrastructure properties: monotone storage, instance bounds, and no NaNs."""
    days = scale_cfg["tiny"]["days"]
    providers = ["aws_like", "azure_like"]
    res_per_provider = scale_cfg["tiny"]["resources_per_provider"]

    world_df, _ = generate_world_timeline(days=days, seed=42)
    infra_df = generate_infra_telemetry(
        world_df=world_df,
        providers=providers,
        resources_per_provider=res_per_provider,
        seed=42,
    )

    # 1. Total row count = total_hours * total_resources
    total_resources = providers_count = len(providers) * res_per_provider
    assert len(infra_df) == (days * 24) * total_resources

    # 2. No nulls or NaNs in any column
    for col in infra_df.columns:
        assert infra_df[col].null_count() == 0, f"Nulls found in {col}"

    # 3. CPU and Memory bounded [0, 100]
    assert (infra_df["x_cpu_pct"] >= 0.0).all()
    assert (infra_df["x_cpu_pct"] <= 100.0).all()
    assert (infra_df["x_mem_pct"] >= 0.0).all()
    assert (infra_df["x_mem_pct"] <= 100.0).all()

    # 4. Instance counts are strictly positive
    assert (infra_df["x_instance_count"] >= 1).all()

    # 5. Storage monotonicity per resource
    # For storage-bearing services (database, object_storage, warehouse), storage should be strictly non-decreasing
    storage_services = ["object_storage", "database", "warehouse"]
    for res_id in infra_df.filter(pl.col("ServiceName").is_in(storage_services))["ResourceId"].unique():
        res_storage = infra_df.filter(pl.col("ResourceId") == res_id)["x_storage_gb"].to_numpy()
        storage_diff = np.diff(res_storage)
        assert (storage_diff >= -1e-6).all(), f"Storage decreased for {res_id}: min diff = {storage_diff.min()}"


def test_infra_reproducibility(scale_cfg):
    """Verify infra generation produces identical outputs with fixed seed."""
    days = scale_cfg["tiny"]["days"]
    world_df, _ = generate_world_timeline(days=days, seed=42)
    infra1 = generate_infra_telemetry(world_df, seed=42, resources_per_provider=6)
    infra2 = generate_infra_telemetry(world_df, seed=42, resources_per_provider=6)

    assert infra1.equals(infra2)
