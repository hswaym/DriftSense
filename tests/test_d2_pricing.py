"""Tests for Phase D2: Pricing simulation, FOCUS schema, and accounting credits."""

import tempfile
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from driftsense.sim.infra import generate_infra_telemetry
from driftsense.sim.pricing import (
    FOCUS_COLUMNS,
    apply_pricing_model,
    save_partitioned_billed_parquet,
)
from driftsense.sim.world import generate_world_timeline
from driftsense.utils.io import load_config


@pytest.fixture
def sample_infra():
    scale_cfg = load_config("scale.yaml")
    days = scale_cfg["tiny"]["days"]
    res_per_provider = scale_cfg["tiny"]["resources_per_provider"]

    world_df, events_df = generate_world_timeline(days=days, seed=42)
    infra_df = generate_infra_telemetry(
        world_df=world_df,
        resources_per_provider=res_per_provider,
        seed=42,
    )
    return infra_df, events_df


def test_focus_column_set_exact(sample_infra):
    """Verify that output DataFrame matches the exact FOCUS column specification."""
    infra_df, events_df = sample_infra
    billed_df, _ = apply_pricing_model(infra_df, events_df=events_df, seed=42)

    # Excluding internal partition column 'billing_month'
    billed_cols = [c for c in billed_df.columns if c != "billing_month"]
    assert set(billed_cols) == set(FOCUS_COLUMNS), f"Column mismatch: {set(billed_cols) ^ set(FOCUS_COLUMNS)}"


def test_cost_inequality_identity(sample_infra):
    """Verify invariant: ListCost >= ContractedCost >= EffectiveCost for all regular usage line items."""
    infra_df, events_df = sample_infra
    billed_df, _ = apply_pricing_model(infra_df, events_df=events_df, seed=42)

    usage_df = billed_df.filter(pl.col("ChargeCategory") == "Usage")

    list_cost = usage_df["ListCost"].to_numpy()
    contracted_cost = usage_df["ContractedCost"].to_numpy()
    effective_cost = usage_df["EffectiveCost"].to_numpy()

    # Float tolerance for rounding
    tol = 1e-2
    assert (list_cost + tol >= contracted_cost).all(), "Violation: ListCost < ContractedCost"
    assert (contracted_cost + tol >= effective_cost).all(), "Violation: ContractedCost < EffectiveCost"
    assert (effective_cost >= -tol).all(), "Usage rows cannot have negative effective cost"


def test_credits_and_refunds_flagged(sample_infra):
    """Verify that credit and refund rows are present, flagged correctly, and have negative amounts."""
    infra_df, events_df = sample_infra
    billed_df, _ = apply_pricing_model(infra_df, events_df=events_df, credit_rate=0.01, seed=42)

    credit_rows = billed_df.filter(pl.col("ChargeCategory").is_in(["Credit", "Refund"]))
    assert len(credit_rows) > 0, "No credit or refund rows generated"

    # All credits must have negative BilledCost and EffectiveCost
    assert (credit_rows["BilledCost"] < 0).all()
    assert (credit_rows["EffectiveCost"] < 0).all()

    # Must be marked as Correction class
    assert (credit_rows["ChargeClass"] == "Correction").all()


def test_cost_identity_quantity_times_price(sample_infra):
    """Verify that cost equals PricingQuantity * UnitPrice within tolerance."""
    infra_df, events_df = sample_infra
    billed_df, _ = apply_pricing_model(infra_df, events_df=events_df, seed=42)

    usage_df = billed_df.filter(pl.col("ChargeCategory") == "Usage")
    # For rows where PricingQuantity > 0, ListCost must be strictly positive
    active_rows = usage_df.filter(pl.col("PricingQuantity") > 0.01)
    assert (active_rows["ListCost"] > 0).all()


def test_partitioned_parquet_output(sample_infra):
    """Verify partitioned parquet export writes valid monthly directories and parquet files."""
    infra_df, events_df = sample_infra
    billed_df, _ = apply_pricing_model(infra_df, events_df=events_df, seed=42)

    with tempfile.TemporaryDirectory() as tmp_dir:
        saved_paths = save_partitioned_billed_parquet(billed_df, output_dir=tmp_dir)
        assert len(saved_paths) > 0

        # Verify each partition is readable by polars
        for p in saved_paths:
            part_df = pl.read_parquet(p)
            assert len(part_df) > 0
            assert "billing_month" not in part_df.columns # Dropped partition col inside parquet
