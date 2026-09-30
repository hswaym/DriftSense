"""Infrastructure simulation module: maps requests to CPU, autoscaling, storage, and egress.

Design Rationale:
- Real infrastructure does not respond instantly to load: autoscalers scale up with
  configured target thresholds (e.g. 70% CPU) and scale down only after a cooldown window
  to prevent flapping/thrashing.
- Storage is inherently cumulative and monotonically non-decreasing over time under normal
  operations (new customer data, audit logs, database snapshots), except during explicit
  retention deletions.
- Network egress is physically bounded by request volume multiplied by response payload distributions.
- 6 services are modeled:
    1. compute: VMs / autoscaling groups
    2. database: relational / transactional DBs with read-replicas and persistent data
    3. object_storage: S3 / Blob storage with cumulative growth and read/write requests
    4. warehouse: analytical processing with diurnal and month-end batch queries
    5. cdn_egress: edge traffic transfer with cache hit ratios
    6. kubernetes: managed container clusters with node pool autoscaling
"""

from datetime import timedelta
from typing import Any, Dict, List, Tuple

import numpy as np
import polars as pl

from driftsense.utils.seed import set_seed


SERVICES: List[str] = [
    "compute",
    "database",
    "object_storage",
    "warehouse",
    "cdn_egress",
    "kubernetes",
]

SERVICE_CATEGORIES: Dict[str, str] = {
    "compute": "Compute",
    "database": "Database",
    "object_storage": "Storage",
    "warehouse": "Analytics",
    "cdn_egress": "Network",
    "kubernetes": "Compute",
}

RESOURCE_TYPES: Dict[str, Dict[str, str]] = {
    "aws_like": {
        "compute": "EC2Instance",
        "database": "RDSInstance",
        "object_storage": "S3Bucket",
        "warehouse": "RedshiftCluster",
        "cdn_egress": "CloudFrontDistribution",
        "kubernetes": "EKSNodeGroup",
    },
    "azure_like": {
        "compute": "VirtualMachine",
        "database": "AzureSQLDatabase",
        "object_storage": "BlobStorage",
        "warehouse": "SynapseWorkspace",
        "cdn_egress": "AzureCDN",
        "kubernetes": "AKSNodePool",
    },
}

CONSUMED_UNITS: Dict[str, str] = {
    "compute": "Hours",
    "database": "Hours",
    "object_storage": "GB-Mo",
    "warehouse": "Hours",
    "cdn_egress": "GB",
    "kubernetes": "Hours",
}


def _simulate_autoscaler(
    requests: np.ndarray,
    capacity_per_instance: float,
    min_instances: int = 2,
    max_instances: int = 40,
    target_cpu: float = 60.0,
    cooldown_hours: int = 3,
) -> Tuple[np.ndarray, np.ndarray]:
    """Simulate a reactive autoscaler with target CPU and cooldown hysteresis.

    Parameters
    ----------
    requests : np.ndarray
        Hourly incoming requests array.
    capacity_per_instance : float
        Requests/hour handled by a single instance at 100% capacity.
    min_instances : int
        Minimum allowed instance count.
    max_instances : int
        Maximum autoscaling boundary.
    target_cpu : float
        Autoscaling target CPU percentage (default 60%).
    cooldown_hours : int
        Number of consecutive hours below threshold before scale-down is permitted.

    Returns
    -------
    Tuple[np.ndarray, np.ndarray]
        (instance_counts, cpu_percentages)
    """
    total_hours = len(requests)
    instance_counts = np.zeros(total_hours, dtype=np.int32)
    cpu_pcts = np.zeros(total_hours, dtype=np.float64)

    current_instances = min_instances
    cooldown_counter = 0

    for t in range(total_hours):
        req = requests[t]
        # Theoretical load on current instances
        # CPU % = base_idle (12%) + (requests / (instances * capacity)) * 75%
        raw_cpu = 12.0 + (req / (max(1, current_instances) * capacity_per_instance)) * 75.0

        if raw_cpu > 72.0 and current_instances < max_instances:
            # Scale UP immediately if over threshold
            needed = int(np.ceil((req / (capacity_per_instance * (target_cpu / 75.0)))))
            current_instances = min(max_instances, max(current_instances + 1, needed))
            cooldown_counter = 0
            # Recalculate CPU with new instances
            raw_cpu = 12.0 + (req / (current_instances * capacity_per_instance)) * 75.0
        elif raw_cpu < 35.0 and current_instances > min_instances:
            # Check cooldown before scale DOWN
            cooldown_counter += 1
            if cooldown_counter >= cooldown_hours:
                # Scale down gradually by at most 20% of fleet
                scale_down_step = max(1, int(current_instances * 0.20))
                current_instances = max(min_instances, current_instances - scale_down_step)
                cooldown_counter = 0
                raw_cpu = 12.0 + (req / (current_instances * capacity_per_instance)) * 75.0
        else:
            cooldown_counter = max(0, cooldown_counter - 1)

        instance_counts[t] = current_instances
        cpu_pcts[t] = float(np.clip(raw_cpu, 5.0, 98.0))

    return instance_counts, cpu_pcts


def generate_infra_telemetry(
    world_df: pl.DataFrame,
    providers: List[str] = ["aws_like", "azure_like"],
    resources_per_provider: int = 6,
    seed: int = 42,
) -> pl.DataFrame:
    """Map world demand into physical infrastructure telemetry across 6 services and providers.

    Parameters
    ----------
    world_df : pl.DataFrame
        Output of world.generate_world_timeline containing timestamps and traffic_requests.
    providers : List[str]
        List of cloud providers to simulate.
    resources_per_provider : int
        Target number of resources per cloud provider.
    seed : int
        Deterministic random seed.

    Returns
    -------
    pl.DataFrame
        Granular hourly infrastructure telemetry for all provisioned cloud resources.
    """
    set_seed(seed)
    rng = np.random.default_rng(seed)

    timestamps = world_df["timestamp"].to_list()
    total_hours = len(timestamps)
    world_reqs = world_df["traffic_requests"].to_numpy().astype(np.float64)
    hour_of_day = world_df["hour_of_day"].to_numpy()
    is_month_end = world_df["is_month_end"].to_numpy()

    # Distribute resources evenly across 6 canonical services
    num_services = len(SERVICES)
    base_count = resources_per_provider // num_services
    rem = resources_per_provider % num_services

    records: List[Dict[str, Any]] = []

    for p_idx, provider in enumerate(providers):
        p_seed = seed + 100 * (p_idx + 1)
        p_rng = np.random.default_rng(p_seed)

        # Provider share (e.g. aws_like 55%, azure_like 45%)
        p_traffic_share = 0.55 if provider == "aws_like" else 0.45

        res_id_counter = 1
        for s_idx, service in enumerate(SERVICES):
            # Number of resources assigned to this service
            n_res = base_count + (1 if s_idx < rem else 0)
            n_res = max(1, n_res)

            for r_sub_idx in range(n_res):
                res_id = f"{provider[:3]}-{service[:4]}-{res_id_counter:03d}"
                res_id_counter += 1
                region = "ap-south-1" if provider == "aws_like" else "central-india"

                # Sub-resource noise factor
                res_weight = (1.0 / n_res) * p_rng.uniform(0.90, 1.10)
                sub_reqs = world_reqs * p_traffic_share * res_weight

                # Telemetry vectors
                x_cpu_pct = np.zeros(total_hours, dtype=np.float64)
                x_mem_pct = np.zeros(total_hours, dtype=np.float64)
                x_requests = np.zeros(total_hours, dtype=np.int64)
                x_storage_gb = np.zeros(total_hours, dtype=np.float64)
                x_egress_gb = np.zeros(total_hours, dtype=np.float64)
                x_instance_count = np.ones(total_hours, dtype=np.int32)
                consumed_quantity = np.zeros(total_hours, dtype=np.float64)

                if service == "compute":
                    cap = p_rng.uniform(85000.0, 120000.0)
                    inst, cpu = _simulate_autoscaler(
                        sub_reqs,
                        capacity_per_instance=cap,
                        min_instances=2,
                        max_instances=35,
                        target_cpu=60.0,
                    )
                    x_instance_count = inst
                    x_cpu_pct = cpu
                    x_requests = sub_reqs.astype(np.int64)
                    x_mem_pct = np.clip(35.0 + 0.45 * cpu + p_rng.normal(0, 1.5, total_hours), 20.0, 95.0)
                    consumed_quantity = x_instance_count.astype(np.float64) * 1.0 # Instance hours

                elif service == "database":
                    # Database: transactional read/write
                    db_reqs = (sub_reqs * 4.2).astype(np.int64)
                    x_requests = db_reqs
                    # Read replica autoscaling (1 to 4 replicas)
                    replica_count = np.clip(1 + (db_reqs / 600000).astype(np.int32), 1, 4)
                    x_instance_count = replica_count
                    x_cpu_pct = np.clip(25.0 + (db_reqs / (replica_count * 500000.0)) * 50.0 + p_rng.normal(0, 2.0, total_hours), 15.0, 95.0)
                    x_mem_pct = np.clip(60.0 + 0.20 * x_cpu_pct, 50.0, 92.0)
                    # Monotone storage growth (base 250 GB + write logs)
                    hourly_growth = p_rng.uniform(0.04, 0.12, total_hours)
                    x_storage_gb = 250.0 + np.cumsum(hourly_growth)
                    consumed_quantity = x_instance_count.astype(np.float64) * 1.0

                elif service == "object_storage":
                    # S3 / Blob storage: cumulative growth is the primary driver
                    x_requests = (sub_reqs * 0.35).astype(np.int64)
                    x_instance_count = np.ones(total_hours, dtype=np.int32)
                    x_cpu_pct = np.clip(5.0 + p_rng.normal(0, 0.5, total_hours), 2.0, 12.0)
                    x_mem_pct = np.clip(10.0 + p_rng.normal(0, 0.5, total_hours), 5.0, 18.0)
                    # Cumulative storage: starts at 1,500 GB, strictly non-decreasing
                    hourly_storage_add = p_rng.uniform(0.15, 0.45, total_hours)
                    x_storage_gb = 1500.0 + np.cumsum(hourly_storage_add)
                    x_egress_gb = np.clip((sub_reqs * 0.00018) + p_rng.normal(0, 0.1, total_hours), 0.05, 500.0)
                    consumed_quantity = x_storage_gb / 730.0 # Standard GB-month prorated hourly

                elif service == "warehouse":
                    # Analytics warehouse: high nightly batch and month-end close
                    is_batch_window = (hour_of_day >= 1) & (hour_of_day <= 4)
                    batch_mult = np.where(is_batch_window, 4.5, 0.8)
                    batch_mult = np.where(is_month_end, batch_mult * 2.2, batch_mult)

                    wh_reqs = (sub_reqs * 0.05 * batch_mult).astype(np.int64)
                    x_requests = wh_reqs
                    x_instance_count = np.where(is_month_end, 4, np.where(is_batch_window, 3, 1)).astype(np.int32)
                    x_cpu_pct = np.clip(
                        np.where(is_batch_window | is_month_end, 75.0, 14.0) + p_rng.normal(0, 3.0, total_hours),
                        5.0, 95.0
                    )
                    x_mem_pct = np.clip(0.85 * x_cpu_pct + 15.0, 20.0, 90.0)
                    # Warehouse storage (accumulates historical partitions)
                    hourly_wh_growth = p_rng.uniform(0.08, 0.25, total_hours)
                    x_storage_gb = 800.0 + np.cumsum(hourly_wh_growth)
                    consumed_quantity = x_instance_count.astype(np.float64) * 1.0

                elif service == "cdn_egress":
                    # CDN edge transfer
                    x_requests = sub_reqs.astype(np.int64)
                    x_instance_count = np.ones(total_hours, dtype=np.int32)
                    # Cache hit ratio 88-92%
                    hit_ratio = 0.90
                    # Egress payload: avg 120 KB per request
                    x_egress_gb = (sub_reqs * 120.0 / (1024.0 * 1024.0)) * (1.0 - hit_ratio)
                    x_cpu_pct = np.clip(15.0 + (sub_reqs / 800000.0) * 30.0, 5.0, 65.0)
                    x_mem_pct = np.clip(25.0 + 0.3 * x_cpu_pct, 15.0, 60.0)
                    consumed_quantity = x_egress_gb

                elif service == "kubernetes":
                    # Container cluster: Node pool autoscaling
                    cap_k8s = p_rng.uniform(90000.0, 130000.0)
                    k8s_inst, k8s_cpu = _simulate_autoscaler(
                        sub_reqs,
                        capacity_per_instance=cap_k8s,
                        min_instances=3,
                        max_instances=30,
                        target_cpu=65.0,
                    )
                    x_instance_count = k8s_inst
                    x_cpu_pct = k8s_cpu
                    x_requests = sub_reqs.astype(np.int64)
                    x_mem_pct = np.clip(45.0 + 0.35 * k8s_cpu + p_rng.normal(0, 2.0, total_hours), 30.0, 95.0)
                    consumed_quantity = x_instance_count.astype(np.float64) * 1.0

                # Append all hourly records for this resource
                for t in range(total_hours):
                    dt_start = timestamps[t]
                    dt_end = dt_start + timedelta(hours=1)
                    records.append({
                        "ChargePeriodStart": dt_start,
                        "ChargePeriodEnd": dt_end,
                        "ProviderName": provider,
                        "SubAccountId": f"acc-{provider[:2]}-001",
                        "ServiceName": service,
                        "ServiceCategory": SERVICE_CATEGORIES[service],
                        "ResourceId": res_id,
                        "ResourceType": RESOURCE_TYPES[provider][service],
                        "RegionId": region,
                        "ConsumedQuantity": float(round(consumed_quantity[t], 4)),
                        "ConsumedUnit": CONSUMED_UNITS[service],
                        "x_cpu_pct": float(round(x_cpu_pct[t], 2)),
                        "x_mem_pct": float(round(x_mem_pct[t], 2)),
                        "x_requests": int(x_requests[t]),
                        "x_storage_gb": float(round(x_storage_gb[t], 4)),
                        "x_egress_gb": float(round(x_egress_gb[t], 4)),
                        "x_instance_count": int(x_instance_count[t]),
                    })

    infra_df = pl.DataFrame(records).sort(["ChargePeriodStart", "ResourceId"])
    return infra_df
