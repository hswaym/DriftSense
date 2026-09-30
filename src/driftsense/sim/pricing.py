"""FOCUS pricing simulation module: converts usage telemetry into multi-tier cloud billing records.

Design Rationale:
- Implements FinOps Foundation FOCUS standard column naming and financial semantics.
- Models pricing tiers: OnDemand, Committed (Reserved/Savings Plan discounts), and Spot.
- Enforces strict cost identity: ListCost >= ContractedCost >= EffectiveCost.
- Introduces legitimate accounting line items: promotional credits and SLA refunds
  with negative BilledCost/EffectiveCost and flagged ChargeCategory.
- Simulates scheduled vendor price reductions, recorded in the events log.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import polars as pl

from driftsense.utils.seed import set_seed


# Base List Unit Prices in INR (per unit specified in CONSUMED_UNITS)
# Hourly basis for Compute, Database, Warehouse, Kubernetes
# GB-month basis for Object Storage; GB basis for CDN Egress
LIST_UNIT_PRICES_INR: Dict[str, Dict[str, float]] = {
    "aws_like": {
        "compute": 4.80,        # INR per instance-hour
        "database": 8.50,       # INR per instance-hour
        "object_storage": 1.90, # INR per GB-month
        "warehouse": 19.50,     # INR per cluster-hour
        "cdn_egress": 6.80,     # INR per GB
        "kubernetes": 5.80,     # INR per node-hour
    },
    "azure_like": {
        "compute": 4.60,
        "database": 8.20,
        "object_storage": 1.80,
        "warehouse": 18.80,
        "cdn_egress": 6.50,
        "kubernetes": 5.60,
    },
}

# Contracted Enterprise Discount (EDP) rate off List Price (~8%)
ENTERPRISE_DISCOUNT_FACTOR = 0.92

# Commitment discount multiplier for Committed tier (~30% off contracted)
COMMITMENT_DISCOUNT_FACTOR = 0.70

FOCUS_COLUMNS = [
    "ChargePeriodStart",
    "ChargePeriodEnd",
    "BillingPeriodStart",
    "BillingPeriodEnd",
    "ProviderName",
    "SubAccountId",
    "ServiceName",
    "ServiceCategory",
    "ResourceId",
    "ResourceType",
    "RegionId",
    "ChargeCategory",
    "ChargeClass",
    "PricingCategory",
    "ConsumedQuantity",
    "ConsumedUnit",
    "PricingQuantity",
    "ListCost",
    "ContractedCost",
    "BilledCost",
    "EffectiveCost",
    "Tags",
    "x_cpu_pct",
    "x_mem_pct",
    "x_requests",
    "x_storage_gb",
    "x_egress_gb",
    "x_instance_count",
]


def apply_pricing_model(
    infra_df: pl.DataFrame,
    events_df: Optional[pl.DataFrame] = None,
    credit_rate: float = 0.003, # 0.3% of rows contain promotional credits / SLA refunds
    seed: int = 42,
) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """Transform infrastructure telemetry into FOCUS-compliant billing records with pricing and credits.

    Parameters
    ----------
    infra_df : pl.DataFrame
        Infrastructure telemetry produced by infra.generate_infra_telemetry.
    events_df : Optional[pl.DataFrame]
        Existing events log to append price change and credit events to.
    credit_rate : float
        Probability of credit/refund line items.
    seed : int
        Deterministic random seed.

    Returns
    -------
    Tuple[pl.DataFrame, pl.DataFrame]
        - billed_df: Enriched DataFrame conforming exactly to FOCUS specification.
        - events_df: Updated discrete event log including price changes.
    """
    set_seed(seed)
    rng = np.random.default_rng(seed)

    total_rows = len(infra_df)
    timestamps = infra_df["ChargePeriodStart"].to_list()
    services = infra_df["ServiceName"].to_list()
    providers = infra_df["ProviderName"].to_list()
    quantities = infra_df["ConsumedQuantity"].to_numpy()
    resource_ids = infra_df["ResourceId"].to_list()

    # Determine Billing Period (calendar month start & end)
    billing_period_starts: List[datetime] = []
    billing_period_ends: List[datetime] = []
    billing_month_keys: List[str] = []

    for dt in timestamps:
        year = dt.year
        month = dt.month
        # Month start
        b_start = datetime(year, month, 1)
        # Month end
        if month == 12:
            b_end = datetime(year + 1, 1, 1)
        else:
            b_end = datetime(year, month + 1, 1)
        billing_period_starts.append(b_start)
        billing_period_ends.append(b_end)
        billing_month_keys.append(f"{year:04d}-{month:02d}")

    # Determine PricingCategory: baseline resources get Committed; dynamic or batch get OnDemand
    # Deterministic assignment based on resource id
    pricing_categories: List[str] = []
    for r_id in resource_ids:
        # e.g. aws-comp-001 -> if suffix is odd, committed; else OnDemand
        try:
            num = int(r_id.split("-")[-1])
            pricing_categories.append("Committed" if num % 2 == 1 else "OnDemand")
        except ValueError:
            pricing_categories.append("OnDemand")

    pricing_cat_arr = np.array(pricing_categories)

    # 1. Base unit prices
    list_unit_prices = np.zeros(total_rows, dtype=np.float64)
    for idx in range(total_rows):
        prov = providers[idx]
        serv = services[idx]
        list_unit_prices[idx] = LIST_UNIT_PRICES_INR.get(prov, {}).get(serv, 5.0)

    # Simulate a mid-year vendor price drop (e.g., 5% price drop starting 2024-07-01)
    price_change_date = datetime(2024, 7, 1)
    price_change_events: List[Dict] = []
    price_drop_mask = np.array([dt >= price_change_date for dt in timestamps])
    list_unit_prices[price_drop_mask] *= 0.95

    # Log price drop event if within timeline
    if any(price_drop_mask):
        price_change_events.append({
            "timestamp": price_change_date,
            "event_type": "price_change",
            "service": "all",
            "metadata": "Annual provider rate revision: 5% across-the-board unit price reduction"
        })

    # 2. Compute ListCost, ContractedCost, EffectiveCost
    # PricingQuantity = ConsumedQuantity
    pricing_quantities = quantities.copy()

    # ListCost = ListUnitPrice * PricingQuantity
    list_costs = list_unit_prices * pricing_quantities

    # ContractedCost = ListCost * EDP Factor
    contracted_costs = list_costs * ENTERPRISE_DISCOUNT_FACTOR

    # EffectiveCost = ContractedCost * (Commitment Factor if Committed else 1.0)
    effective_costs = contracted_costs.copy()
    is_committed = pricing_cat_arr == "Committed"
    effective_costs[is_committed] *= COMMITMENT_DISCOUNT_FACTOR

    # BilledCost is what is invoiced for the period:
    # OnDemand is billed directly as contracted cost.
    # Committed is billed under amortized effective cost.
    billed_costs = np.where(is_committed, effective_costs, contracted_costs)

    # 3. Charge Category and Class
    charge_categories = ["Usage"] * total_rows
    charge_classes = ["Original"] * total_rows

    # 4. Inject legitimate credits and SLA refunds (negative cost rows)
    credit_mask = rng.random(total_rows) < credit_rate
    num_credits = int(np.sum(credit_mask))

    charge_period_ends = infra_df["ChargePeriodEnd"].to_list()
    sub_account_ids = infra_df["SubAccountId"].to_list()
    service_categories = infra_df["ServiceCategory"].to_list()
    resource_types = infra_df["ResourceType"].to_list()
    region_ids = infra_df["RegionId"].to_list()
    consumed_units = infra_df["ConsumedUnit"].to_list()
    storage_gbs = infra_df["x_storage_gb"].to_list()

    credit_rows_to_append: List[Dict[str, Any]] = []

    for idx_raw in np.where(credit_mask)[0]:
        idx = int(idx_raw)
        credit_type = rng.choice(["Credit", "Refund"])
        # Magnitude is 20% to 80% of the associated row cost
        credit_mag = float(round(billed_costs[idx] * rng.uniform(0.20, 0.80), 2))
        if credit_mag <= 0.01:
            credit_mag = 10.50

        credit_record = {
            "ChargePeriodStart": timestamps[idx],
            "ChargePeriodEnd": charge_period_ends[idx],
            "BillingPeriodStart": billing_period_starts[idx],
            "BillingPeriodEnd": billing_period_ends[idx],
            "ProviderName": providers[idx],
            "SubAccountId": sub_account_ids[idx],
            "ServiceName": services[idx],
            "ServiceCategory": service_categories[idx],
            "ResourceId": resource_ids[idx],
            "ResourceType": resource_types[idx],
            "RegionId": region_ids[idx],
            "ChargeCategory": credit_type,
            "ChargeClass": "Correction",
            "PricingCategory": pricing_categories[idx],
            "ConsumedQuantity": 0.0,
            "ConsumedUnit": consumed_units[idx],
            "PricingQuantity": 0.0,
            "ListCost": 0.0,
            "ContractedCost": -credit_mag,
            "BilledCost": -credit_mag,
            "EffectiveCost": -credit_mag,
            "Tags": '{"env": "prod", "credit_type": "sla_discount"}',
            "x_cpu_pct": 0.0,
            "x_mem_pct": 0.0,
            "x_requests": 0,
            "x_storage_gb": float(storage_gbs[idx]),
            "x_egress_gb": 0.0,
            "x_instance_count": 0,
            "billing_month": billing_month_keys[idx],
        }
        credit_rows_to_append.append(credit_record)

    # Standard resource tags
    tags = [f'{{"env": "prod", "tier": "{pricing_cat_arr[i].lower()}"}}' for i in range(total_rows)]

    # Assemble base billed dataframe
    base_billed_df = infra_df.with_columns([
        pl.Series("BillingPeriodStart", billing_period_starts),
        pl.Series("BillingPeriodEnd", billing_period_ends),
        pl.Series("ChargeCategory", charge_categories),
        pl.Series("ChargeClass", charge_classes),
        pl.Series("PricingCategory", pricing_categories),
        pl.Series("PricingQuantity", np.round(pricing_quantities, 4)),
        pl.Series("ListCost", np.round(list_costs, 2)),
        pl.Series("ContractedCost", np.round(contracted_costs, 2)),
        pl.Series("BilledCost", np.round(billed_costs, 2)),
        pl.Series("EffectiveCost", np.round(effective_costs, 2)),
        pl.Series("Tags", tags),
        pl.Series("billing_month", billing_month_keys),
    ])

    # Reorder base dataframe to exact FOCUS columns + billing_month
    cols_order = [c for c in FOCUS_COLUMNS if c in base_billed_df.columns] + ["billing_month"]
    base_billed_df = base_billed_df.select(cols_order)

    # Combine with credit rows if any
    if credit_rows_to_append:
        credit_df = pl.DataFrame(credit_rows_to_append).select(cols_order)
        final_billed_df = pl.concat([base_billed_df, credit_df]).sort(["ChargePeriodStart", "ResourceId"])
    else:
        final_billed_df = base_billed_df.sort(["ChargePeriodStart", "ResourceId"])

    # Update events dataframe
    if price_change_events:
        new_events = pl.DataFrame(price_change_events)
        if events_df is not None and len(events_df) > 0:
            updated_events_df = pl.concat([events_df, new_events]).sort("timestamp")
        else:
            updated_events_df = new_events.sort("timestamp")
    else:
        updated_events_df = events_df if events_df is not None else pl.DataFrame()

    return final_billed_df, updated_events_df


def save_partitioned_billed_parquet(billed_df: pl.DataFrame, output_dir: str = "data/raw") -> List[str]:
    """Save billed parquet files partitioned by billing_month.

    Parameters
    ----------
    billed_df : pl.DataFrame
        Billed DataFrame containing 'billing_month' column.
    output_dir : str
        Base destination directory.

    Returns
    -------
    List[str]
        List of generated parquet partition file paths.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    saved_paths: List[str] = []
    months = billed_df["billing_month"].unique().sort().to_list()

    for month_str in months:
        month_part_dir = out_path / f"billing_month={month_str}"
        month_part_dir.mkdir(parents=True, exist_ok=True)
        file_path = month_part_dir / "data.parquet"

        part_df = billed_df.filter(pl.col("billing_month") == month_str).drop("billing_month")
        part_df.write_parquet(file_path)
        saved_paths.append(str(file_path))

    return saved_paths
