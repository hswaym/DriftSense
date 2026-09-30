# Dataset Card: DriftBench-v1

## 1. Overview
- **Name**: DriftBench-v1
- **Domain**: Cloud Billing & Observability Telemetry (FinOps)
- **Granularity**: Hourly
- **Providers**: 2 (`aws_like`, `azure_like`)
- **Services**: 6 (`compute`, `database`, `object_storage`, `warehouse`, `cdn_egress`, `kubernetes`)
- **Time Span**: 365 days (Full scale ~0.7M rows hourly)
- **Primary Schema**: Standardized against FinOps Foundation **FOCUS** specifications.

---

## 2. Schema Specification

### Primary Billing & Telemetry Table (FOCUS + System Telemetry)

| Column Name | Type | Description | Sample Values / Constraints |
|---|---|---|---|
| `ChargePeriodStart` | timestamp (UTC) | Start of the hourly billing window | `2024-01-01 00:00:00` |
| `ChargePeriodEnd` | timestamp (UTC) | End of the hourly billing window | `2024-01-01 01:00:00` |
| `BillingPeriodStart` | date | Start of the calendar billing month | `2024-01-01` |
| `BillingPeriodEnd` | date | End of the calendar billing month | `2024-01-31` |
| `ProviderName` | string | Cloud service provider identifier | `aws_like`, `azure_like` |
| `SubAccountId` | string | Account/Subscription identifier | `acc-001`, `sub-az-102` |
| `ServiceName` | string | Cloud service category | `compute`, `database`, `object_storage`, `warehouse`, `cdn_egress`, `kubernetes` |
| `ServiceCategory` | string | Functional category | `Compute`, `Storage`, `Network`, `Database` |
| `ResourceId` | string | Unique cloud resource identifier | `res-vm-049`, `res-db-012` |
| `ResourceType` | string | Granular resource classification | `VirtualMachine`, `ManagedDB`, `BlobContainer` |
| `RegionId` | string | Deployment region | `ap-south-1`, `central-india` |
| `ChargeCategory` | string | Nature of charge | `Usage`, `Credit`, `Refund` |
| `ChargeClass` | string | Accounting classification | `Correction`, `Original` |
| `PricingCategory` | string | Commitment tier | `OnDemand`, `Committed`, `Spot` |
| `ConsumedQuantity` | float | Measured raw usage | Positive float |
| `ConsumedUnit` | string | Canonical usage unit | `Hours`, `GB`, `Requests`, `vCPUHours` |
| `PricingQuantity` | float | Billed quantity | Equals `ConsumedQuantity` |
| `ListCost` | float | Undiscounted list price (INR) | $ListCost \ge ContractedCost \ge EffectiveCost$ |
| `ContractedCost` | float | Negotiated customer cost (INR) | Non-negative (negative for refunds/credits) |
| `BilledCost` | float | Invoice amount (INR) | Invoiced amount |
| `EffectiveCost` | float | True amortized cost after discounts | True cost |
| `Tags` | json / string | Key-value resource tags | `{"env": "prod", "team": "data"}` |
| `x_cpu_pct` | float | Observed average CPU utilization | $[0.0, 100.0]$ |
| `x_mem_pct` | float | Observed memory utilization | $[0.0, 100.0]$ |
| `x_requests` | int | Total incoming service requests | Count |
| `x_storage_gb` | float | Total cumulative stored bytes in GB | Monotone growth |
| `x_egress_gb` | float | Total network transfer out in GB | Non-negative |
| `x_instance_count` | int | Autoscaled active instances | Positive integer |

---

## 3. Side Tables

### 1. `ground_truth`
Contains incident windows and root cause labels for evaluation.
- `incident_id`: string (`inc-001`)
- `start`: timestamp UTC
- `end`: timestamp UTC
- `service`: string
- `root_cause`: string (`deployment_regression`, `autoscaling_runaway`, `traffic_surge`, `storage_leak`, `instance_upsize`, `egress_spike`)
- `propagated_services`: list/string
- `magnitude_inr`: float
- `is_decoy`: boolean (True for sales, month-end batches, holiday dips)

### 2. `events`
Observability event log:
- `timestamp`: UTC timestamp
- `event_type`: `deployment`, `config_change`, `sale_start`, `sale_end`, `holiday`
- `service`: affected service
- `metadata`: JSON payload

### 3. `dirt_log`
Complete audit log of synthetic corruptions injected to test cleaning recovery:
- `row_id`: identifier
- `corruption_type`: string
- `original_value`: string / float
- `corrupted_value`: string / float
- `timestamp`: UTC timestamp

### 4. `clean_truth`
Pristine, pre-corruption baseline parquet dataset used strictly as ground truth to evaluate cleaning recovery rates.
