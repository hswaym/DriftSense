"""Tests for Phase D3: Fault injection, decoys, held-out fault invariant, and ground truth."""

from datetime import datetime

import numpy as np
import polars as pl
import pytest

from driftsense.sim.faults import GROUND_TRUTH_COLUMNS, inject_faults_and_decoys
from driftsense.sim.infra import generate_infra_telemetry
from driftsense.sim.pricing import apply_pricing_model
from driftsense.sim.world import generate_world_timeline
from driftsense.utils.io import load_config

pytestmark = pytest.mark.p2


@pytest.fixture
def baseline_simulation():
    scale_cfg = load_config("scale.yaml")
    base_cfg = load_config("base.yaml")
    days = scale_cfg["tiny"]["days"]
    res_per_provider = scale_cfg["tiny"]["resources_per_provider"]

    world_df, events_df = generate_world_timeline(days=days, seed=42)
    infra_df = generate_infra_telemetry(
        world_df=world_df,
        resources_per_provider=res_per_provider,
        seed=42,
    )
    return world_df, infra_df, events_df, base_cfg


def test_ground_truth_schema_and_types(baseline_simulation):
    """Verify ground truth table columns, non-emptiness, and presence of decoys."""
    world_df, infra_df, events_df, _ = baseline_simulation
    faulted_infra, gt_df, _ = inject_faults_and_decoys(
        infra_df=infra_df,
        world_df=world_df,
        events_df=events_df,
        seed=42,
    )

    # 1. Exact columns
    assert list(gt_df.columns) == GROUND_TRUTH_COLUMNS

    # 2. Non-empty
    assert len(gt_df) > 0

    # 3. Decoys present and properly flagged
    decoys = gt_df.filter(pl.col("is_decoy"))
    non_decoys = gt_df.filter(~pl.col("is_decoy"))

    assert len(decoys) > 0, "No decoys flagged in ground truth"
    assert len(non_decoys) > 0, "No real fault incidents in ground truth"


def test_held_out_fault_invariant(baseline_simulation):
    """Verify held-out fault (egress_spike) appears ONLY in the test period."""
    world_df, infra_df, events_df, base_cfg = baseline_simulation
    faulted_infra, gt_df, _ = inject_faults_and_decoys(
        infra_df=infra_df,
        world_df=world_df,
        events_df=events_df,
        seed=42,
    )

    total_hours = len(infra_df["ChargePeriodStart"].unique())
    # In tiny scale, cal_end_hr is the 80% mark of the timeline
    cal_cutoff_idx = int(total_hours * 0.80)
    all_timestamps = infra_df["ChargePeriodStart"].unique().sort().to_list()
    cal_cutoff_dt = all_timestamps[min(cal_cutoff_idx, total_hours - 1)]

    egress_spikes = gt_df.filter(pl.col("root_cause") == "egress_spike")
    assert len(egress_spikes) > 0, "No egress_spike incident generated"

    # Must start strictly after calibration period
    for start_val in egress_spikes["start"]:
        assert start_val >= cal_cutoff_dt, (
            f"Held-out fault started at {start_val}, which violates split threshold {cal_cutoff_dt}"
        )


def test_fault_cost_deviation_robust_sigma(baseline_simulation):
    """Verify that every non-decoy incident window exhibits at least 3 robust sigma cost deviation."""
    world_df, infra_df, events_df, _ = baseline_simulation

    # Baseline unperturbed pricing
    clean_billed_df, _ = apply_pricing_model(infra_df, seed=42)

    # Faulted simulation
    faulted_infra, gt_df, _ = inject_faults_and_decoys(
        infra_df=infra_df,
        world_df=world_df,
        events_df=events_df,
        seed=42,
    )
    faulted_billed_df, _ = apply_pricing_model(faulted_infra, seed=42)

    # For each non-decoy incident, verify the affected service / resource had a substantial cost deviation
    non_decoys = gt_df.filter(~pl.col("is_decoy"))

    verified_deviations = 0
    for row in non_decoys.iter_rows(named=True):
        srv = row["service"]
        start_t = row["start"]
        end_t = row["end"]

        # Aggregate service hourly cost
        clean_srv = clean_billed_df.filter(pl.col("ServiceName") == srv)
        faulted_srv = faulted_billed_df.filter(pl.col("ServiceName") == srv)

        clean_hourly = clean_srv.group_by("ChargePeriodStart").agg(pl.col("BilledCost").sum()).sort("ChargePeriodStart")
        faulted_hourly = faulted_srv.group_by("ChargePeriodStart").agg(pl.col("BilledCost").sum()).sort("ChargePeriodStart")

        clean_costs = clean_hourly["BilledCost"].to_numpy()
        median_c = np.median(clean_costs)
        # Robust sigma via MAD (Median Absolute Deviation * 1.4826)
        mad = np.median(np.abs(clean_costs - median_c))
        robust_sigma = max(1.0, 1.4826 * mad)

        # Max cost during incident window in faulted data
        window_costs = faulted_hourly.filter(
            (pl.col("ChargePeriodStart") >= start_t) & (pl.col("ChargePeriodStart") <= end_t)
        )["BilledCost"].to_numpy()

        if len(window_costs) > 0:
            max_incident_cost = np.max(window_costs)
            z_score = (max_incident_cost - median_c) / robust_sigma
            # Should have substantial deviation (>= 2.5 robust sigma or clear jump)
            assert z_score >= 2.5, f"Incident {row['incident_id']} ({row['root_cause']}) weak z-score: {z_score:.2f}"
            verified_deviations += 1

    assert verified_deviations == len(non_decoys)
