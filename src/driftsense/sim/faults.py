"""Fault injection module: injects root-cause anomalies and decoys at the telemetry layer.

Design Rationale:
- Ground-truth anomalies MUST be injected into the underlying physical metrics
  (requests, CPU, instance count, storage growth rate, network egress) rather than directly
  into cost columns. This guarantees that telemetry and cost move together organically.
- 6 Fault Types:
    1. deployment_regression (step): CPU usage doubles due to inefficient code push.
    2. autoscaling_runaway (ramp): instance count climbs steadily due to misconfigured health checks.
    3. traffic_surge (decay): sudden viral request burst with exponential decay.
    4. storage_leak (ramp): cumulative storage accumulates at 5x-10x normal rate.
    5. instance_upsize (step): uncoordinated fleet upsize/overprovisioning.
    6. egress_spike (step): CDN cache bypass causing massive outbound bandwidth spike.
- Held-Out Invariant:
    `egress_spike` appears ONLY in the test split period (never in train or calibration).
- Decoys (is_decoy=True):
    Legitimate demand increases (sales, month-end close) recorded to evaluate false-alarm rejection.
- Overlapping & Confounded Scenarios:
    ~15% overlap rate; confounded deployment + traffic surge scenarios on the same date.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import polars as pl

from driftsense.sim.infra import CONSUMED_UNITS
from driftsense.sim.pricing import apply_pricing_model
from driftsense.utils.io import load_config
from driftsense.utils.seed import set_seed


GROUND_TRUTH_COLUMNS = [
    "incident_id",
    "start",
    "end",
    "service",
    "root_cause",
    "propagated_services",
    "magnitude_inr",
    "is_decoy",
]


def _generate_shape_profile(shape: str, duration: int, max_multiplier: float) -> np.ndarray:
    """Generate time-series multiplier envelope for the given duration."""
    t = np.arange(duration, dtype=np.float64)
    if shape == "step":
        return np.full(duration, max_multiplier, dtype=np.float64)
    elif shape == "ramp":
        # Linear growth from 1.0 to max_multiplier
        if duration == 1:
            return np.array([max_multiplier], dtype=np.float64)
        return 1.0 + (max_multiplier - 1.0) * (t / (duration - 1))
    elif shape == "decay":
        # Immediate spike with exponential decay
        decay_rate = 3.0 / max(1, duration)
        return 1.0 + (max_multiplier - 1.0) * np.exp(-decay_rate * t)
    else:
        return np.full(duration, max_multiplier, dtype=np.float64)


def inject_faults_and_decoys(
    infra_df: pl.DataFrame,
    world_df: pl.DataFrame,
    events_df: Optional[pl.DataFrame] = None,
    faults_config_path: str = "faults.yaml",
    base_config_path: str = "base.yaml",
    seed: int = 42,
) -> Tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Inject configured faults and decoys into infrastructure telemetry and generate ground truth.

    Parameters
    ----------
    infra_df : pl.DataFrame
        Uncorrupted infrastructure telemetry from infra.generate_infra_telemetry.
    world_df : pl.DataFrame
        World timeline DataFrame from world.generate_world_timeline.
    events_df : Optional[pl.DataFrame]
        Discrete event log.
    faults_config_path : str
        Path or filename for faults YAML config.
    base_config_path : str
        Path or filename for base YAML config.
    seed : int
        Deterministic random seed.

    Returns
    -------
    Tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]
        - faulted_infra_df: Telemetry with physical metrics perturbed by incidents.
        - ground_truth_df: Canonical table of all incidents and decoys.
        - updated_events_df: Discrete events log updated with incident deployments.
    """
    set_seed(seed)
    rng = np.random.default_rng(seed)

    faults_cfg = load_config(faults_config_path)
    base_cfg = load_config(base_config_path)

    # Determine timeline boundaries and split dates
    all_timestamps = infra_df["ChargePeriodStart"].unique().sort().to_list()
    total_hours = len(all_timestamps)
    start_dt = all_timestamps[0]
    end_dt = all_timestamps[-1]
    timeline_days = max(1, int(total_hours / 24))

    # Split thresholds
    train_end_str = base_cfg.get("splits", {}).get("train_end", "2024-08-31 23:00:00")
    cal_end_str = base_cfg.get("splits", {}).get("cal_end", "2024-10-31 23:00:00")
    train_end_dt = datetime.strptime(train_end_str, "%Y-%m-%d %H:%M:%S")
    cal_end_dt = datetime.strptime(cal_end_str, "%Y-%m-%d %H:%M:%S")

    # If running on small/tiny scale (e.g. <= 90 days), scale split thresholds proportionally
    if timeline_days < 365:
        # Train: first 60% of timeline, Cal: next 20%, Test: last 20%
        train_cutoff_hr = int(total_hours * 0.60)
        cal_cutoff_hr = int(total_hours * 0.80)
        train_end_dt = all_timestamps[min(train_cutoff_hr, total_hours - 1)]
        cal_end_dt = all_timestamps[min(cal_cutoff_hr, total_hours - 1)]

    # Incident frequency targets scaled to timeline length
    scale_factor = timeline_days / 365.0
    target_annual_per_type = faults_cfg["incident_frequency"]["target_incidents_per_type_annual"]
    target_incidents_per_type = max(1, int(round(target_annual_per_type * scale_factor)))
    target_decoys = max(1, int(round(faults_cfg["incident_frequency"]["target_decoys_annual"] * scale_factor)))

    # Work with mutable copies of column lists for vectorized-equivalent batch updates
    res_ids = infra_df["ResourceId"].to_list()
    services = infra_df["ServiceName"].to_list()
    dt_starts = infra_df["ChargePeriodStart"].to_list()
    dt_ends = infra_df["ChargePeriodEnd"].to_list()
    cpu_vals = infra_df["x_cpu_pct"].to_numpy().copy()
    mem_vals = infra_df["x_mem_pct"].to_numpy().copy()
    req_vals = infra_df["x_requests"].to_numpy().copy()
    storage_vals = infra_df["x_storage_gb"].to_numpy().copy()
    egress_vals = infra_df["x_egress_gb"].to_numpy().copy()
    inst_vals = infra_df["x_instance_count"].to_numpy().copy()
    consumed_vals = infra_df["ConsumedQuantity"].to_numpy().copy()

    # Pre-build lookup: resource_id -> row indices sorted by time
    res_to_indices: Dict[str, List[int]] = {}
    for idx, r_id in enumerate(res_ids):
        res_to_indices.setdefault(r_id, []).append(idx)

    service_to_resources: Dict[str, List[str]] = {}
    for r_id, indices in res_to_indices.items():
        srv = services[indices[0]]
        service_to_resources.setdefault(srv, []).append(r_id)

    ground_truth_records: List[Dict[str, Any]] = []
    incident_counter = 1

    # 1. Schedule Fault Incidents
    for fault_name, fault_info in faults_cfg["fault_types"].items():
        is_held_out = fault_info.get("held_out", False)
        shape = fault_info["shape"]
        candidate_services = fault_info["services"]
        d_min, d_max = fault_info["duration_hours_range"]
        m_min, m_max = fault_info["severity_multiplier_range"]

        # Number of incidents for this fault type
        n_incidents = target_incidents_per_type

        for _ in range(n_incidents):
            # Select target service and primary resource
            target_service = rng.choice(candidate_services)
            avail_resources = service_to_resources.get(target_service, [])
            if not avail_resources:
                continue
            target_res = rng.choice(avail_resources)
            target_indices = res_to_indices[target_res]
            n_target_hours = len(target_indices)

            # Determine duration
            duration = int(rng.integers(d_min, max(d_min + 1, d_max + 1)))
            duration = min(duration, max(2, n_target_hours // 2))

            # Select start time satisfying held_out constraint
            if is_held_out:
                # MUST start in test period (after cal_end_dt)
                valid_start_indices = [
                    i for i in range(n_target_hours - duration)
                    if dt_starts[target_indices[i]] > cal_end_dt
                ]
            else:
                # Can start anywhere with enough buffer
                valid_start_indices = list(range(max(1, n_target_hours - duration)))

            if not valid_start_indices:
                # Fallback to final available window if test period is very tight
                start_offset = max(0, n_target_hours - duration - 1)
            else:
                start_offset = int(rng.choice(valid_start_indices))

            start_time = dt_starts[target_indices[start_offset]]
            end_time = dt_ends[target_indices[start_offset + duration - 1]]

            multiplier = float(rng.uniform(m_min, m_max))
            profile = _generate_shape_profile(shape, duration, multiplier)

            propagated: List[str] = []

            # Apply fault perturbation to physical telemetry
            for step_idx in range(duration):
                row_idx = target_indices[start_offset + step_idx]
                mult = profile[step_idx]

                if fault_name == "deployment_regression":
                    # CPU steps up; autoscaler increases instances to compensate
                    cpu_vals[row_idx] = np.clip(cpu_vals[row_idx] * mult, 10.0, 98.0)
                    inst_vals[row_idx] = max(1, int(np.ceil(inst_vals[row_idx] * (1.0 + 0.40 * (mult - 1.0)))))
                    consumed_vals[row_idx] = float(inst_vals[row_idx])

                elif fault_name == "autoscaling_runaway":
                    # Instance count ramps up dramatically; CPU may slightly drop due to overprovisioning
                    inst_vals[row_idx] = max(1, int(np.ceil(inst_vals[row_idx] * mult)))
                    cpu_vals[row_idx] = np.clip(cpu_vals[row_idx] / np.sqrt(mult), 12.0, 95.0)
                    consumed_vals[row_idx] = float(inst_vals[row_idx])

                elif fault_name == "traffic_surge":
                    # Requests surge, propagating to autoscaler instances or CDN egress
                    req_vals[row_idx] = int(req_vals[row_idx] * mult)
                    cpu_vals[row_idx] = np.clip(cpu_vals[row_idx] * (1.0 + 0.30 * (mult - 1.0)), 15.0, 98.0)
                    if target_service == "cdn_egress":
                        egress_vals[row_idx] = float(egress_vals[row_idx] * mult)
                        consumed_vals[row_idx] = float(egress_vals[row_idx])
                    else:
                        inst_mult = 1.0 + 0.85 * (mult - 1.0)
                        inst_vals[row_idx] = max(1, int(np.ceil(inst_vals[row_idx] * inst_mult)))
                        consumed_vals[row_idx] = float(inst_vals[row_idx])

                elif fault_name == "storage_leak":
                    # Accelerate cumulative storage additions significantly
                    leak_rate_gb = 180.0 * mult
                    # All subsequent hours inherit cumulative leak
                    subsequent_indices = target_indices[start_offset + step_idx:]
                    storage_vals[subsequent_indices] += leak_rate_gb
                    for s_i in subsequent_indices:
                        consumed_vals[s_i] = float(storage_vals[s_i] / 730.0)

                elif fault_name == "instance_upsize":
                    # Unauthorized capacity doubling
                    inst_vals[row_idx] = max(1, int(np.ceil(inst_vals[row_idx] * mult)))
                    consumed_vals[row_idx] = float(inst_vals[row_idx])

                elif fault_name == "egress_spike":
                    # Massive CDN egress spike
                    egress_vals[row_idx] = float(egress_vals[row_idx] * mult)
                    consumed_vals[row_idx] = float(egress_vals[row_idx])

            # Record non-decoy incident in ground truth
            inc_id = f"inc-{incident_counter:03d}"
            incident_counter += 1

            ground_truth_records.append({
                "incident_id": inc_id,
                "start": start_time,
                "end": end_time,
                "service": target_service,
                "root_cause": fault_name,
                "propagated_services": ",".join(propagated) if propagated else target_service,
                "magnitude_inr": float(round(multiplier * 1500.0, 2)),
                "is_decoy": False,
            })

    # 2. Confounded Incident (Deployment + Traffic Surge same day; true cause = traffic_surge)
    confounded_res = service_to_resources.get("compute", [])
    if confounded_res:
        conf_target = confounded_res[0]
        c_indices = res_to_indices[conf_target]
        c_dur = 12
        c_start_offset = max(2, len(c_indices) // 3)
        c_start_dt = dt_starts[c_indices[c_start_offset]]
        c_end_dt = dt_ends[c_indices[c_start_offset + c_dur - 1]]

        # Inject traffic surge (the true root cause)
        for step_idx in range(c_dur):
            r_idx = c_indices[c_start_offset + step_idx]
            req_vals[r_idx] = int(req_vals[r_idx] * 3.5)
            cpu_vals[r_idx] = np.clip(cpu_vals[r_idx] * 2.0, 25.0, 98.0)
            inst_vals[r_idx] = max(1, int(inst_vals[r_idx] * 2))
            consumed_vals[r_idx] = float(inst_vals[r_idx])

        # Log confounded incident with true cause = traffic_surge
        inc_id = f"inc-{incident_counter:03d}"
        incident_counter += 1
        ground_truth_records.append({
            "incident_id": inc_id,
            "start": c_start_dt,
            "end": c_end_dt,
            "service": "compute",
            "root_cause": "traffic_surge",
            "propagated_services": "compute,database",
            "magnitude_inr": 4500.0,
            "is_decoy": False,
        })

        # Add a distracting CI/CD release deployment at the exact same hour
        if events_df is not None:
            confounded_event = pl.DataFrame([{
                "timestamp": c_start_dt,
                "event_type": "deployment",
                "service": "compute",
                "metadata": "Confounded CI/CD release v2.4.0 (coincidental with traffic surge)"
            }])
            events_df = pl.concat([events_df, confounded_event]).sort("timestamp")

    # 3. Schedule Benign Decoys (is_decoy = True)
    # Check if calendar sales or month-end batches already exist in world_df
    sale_times = world_df.filter(pl.col("is_sale_event"))["timestamp"].to_list()
    month_end_times = world_df.filter(pl.col("is_month_end"))["timestamp"].to_list()

    if sale_times:
        d_start = sale_times[0]
        d_end = sale_times[min(len(sale_times) - 1, 48)]
        ground_truth_records.append({
            "incident_id": f"decoy-{incident_counter:03d}",
            "start": d_start,
            "end": d_end,
            "service": "all",
            "root_cause": "sale_event",
            "propagated_services": "compute,database,cdn_egress",
            "magnitude_inr": 8500.0,
            "is_decoy": True,
        })
        incident_counter += 1
    else:
        # Guarantee at least one benign sale decoy on short/tiny scales
        d_idx = min(len(dt_starts) - 1, max(12, total_hours // 4))
        d_start = dt_starts[d_idx]
        d_end = dt_ends[min(len(dt_ends) - 1, d_idx + 24)]
        ground_truth_records.append({
            "incident_id": f"decoy-{incident_counter:03d}",
            "start": d_start,
            "end": d_end,
            "service": "compute",
            "root_cause": "sale_event",
            "propagated_services": "compute,database",
            "magnitude_inr": 6200.0,
            "is_decoy": True,
        })
        incident_counter += 1

    if month_end_times:
        m_start = month_end_times[0]
        m_end = month_end_times[min(len(month_end_times) - 1, 24)]
        ground_truth_records.append({
            "incident_id": f"decoy-{incident_counter:03d}",
            "start": m_start,
            "end": m_end,
            "service": "warehouse",
            "root_cause": "month_end_batch",
            "propagated_services": "warehouse,compute",
            "magnitude_inr": 3800.0,
            "is_decoy": True,
        })
        incident_counter += 1
    else:
        # Guarantee at least one month-end batch decoy on short/tiny scales
        m_idx = min(len(dt_starts) - 1, max(24, total_hours // 2))
        m_start = dt_starts[m_idx]
        m_end = dt_ends[min(len(dt_ends) - 1, m_idx + 12)]
        ground_truth_records.append({
            "incident_id": f"decoy-{incident_counter:03d}",
            "start": m_start,
            "end": m_end,
            "service": "warehouse",
            "root_cause": "month_end_batch",
            "propagated_services": "warehouse,compute",
            "magnitude_inr": 3800.0,
            "is_decoy": True,
        })
        incident_counter += 1

    # Reassemble mutated infrastructure dataframe
    faulted_infra_df = infra_df.with_columns([
        pl.Series("x_cpu_pct", cpu_vals),
        pl.Series("x_mem_pct", mem_vals),
        pl.Series("x_requests", req_vals),
        pl.Series("x_storage_gb", storage_vals),
        pl.Series("x_egress_gb", egress_vals),
        pl.Series("x_instance_count", inst_vals),
        pl.Series("ConsumedQuantity", consumed_vals),
    ])

    ground_truth_df = pl.DataFrame(ground_truth_records).select(GROUND_TRUTH_COLUMNS).sort("start")
    updated_events_df = events_df if events_df is not None else pl.DataFrame()

    return faulted_infra_df, ground_truth_df, updated_events_df
