# Cleaning Specification: DriftSense Silver & Gold Pipeline

## 1. Core Principles & Non-Negotiables
1. **Never Delete Cost Spikes**: Anomalies are our detection targets. Deleting them destroys ground truth. Any unresolvable, corrupt, or suspicious rows MUST be isolated into `quarantine.parquet`.
2. **Never Silently Impute Cost**: Imputing cost fabricates financial liabilities. Missing usage can only be linearly interpolated for brief gaps ($\le 3$ hours) and explicitly flagged with `is_imputed=True`. Long gaps are masked.
3. **Preserve Accounting Realities**: Legitimate credits and refunds (negative `BilledCost` and `EffectiveCost`) must be preserved and verified via `ChargeCategory`.

---

## 2. Nine-Step Ordered Cleaning Pipeline (Bronze -> Silver)

```
Bronze Raw Bills (with injected dirt)
   │
   ▼
[Step 1] Schema Harmonization & Dtype Casting
   │      - Harmonize provider variations (e.g. CostInBillingCurrency -> BilledCost)
   │      - Strict dtype enforcement (timestamps, floats, categorical strings)
   ▼
[Step 2] Timezone Standardization
   │      - Convert all provider timestamps to standardized UTC (e.g. IST +05:30 -> UTC)
   ▼
[Step 3] Unit Normalization
   │      - Standardize GiB / bytes / MB into canonical GB
   │      - Align unit prices proportionally
   ▼
[Step 4] Deduplication
   │      - Deduplicate on (ChargePeriodStart, ResourceId, ChargeCategory, line_hash)
   │      - Flag duplicate occurrences in audit log
   ▼
[Step 5] Late Ingest Restatements
   │      - For restated bills, latest ingestion timestamp takes precedence
   ▼
[Step 6] Missing Usage Handling
   │      - Gaps <= 3 hours: linear interpolation on usage only, marked with is_imputed=True
   │      - Gaps > 3 hours: masked and flagged, never imputed
   │      - Cost is NEVER imputed silently
   ▼
[Step 7] Outlier & Sensor Glitch Triage
   │      - Clip or quarantine physically impossible telemetry (e.g. CPU > 100%)
   │      - Quarantine rows with null ResourceId or corrupted non-recoverable identifiers
   │      - Real cost spikes are retained in Silver
   ▼
[Step 8] Pandera Contract Validation
   │      - Execute strict schema validation on Silver dataset
   ▼
[Step 9] Recovery Scoring & Data Quality Report
          - Compare Silver against clean_truth using dirt_log
          - Quantify recovery rate per corruption type (Target: >= 90% on fixable types)
          - Verify 100% of ground_truth incident windows remain intact
```

---

## 3. Quarantine Policy (`data/clean/quarantine.parquet`)
Rows quarantined must preserve the raw payload alongside:
- `quarantine_reason`: e.g. `PHYSICALLY_IMPOSSIBLE_METRIC`, `UNRESOLVABLE_RESOURCE_ID`, `MALFORMED_TIMESTAMP`
- `detected_at`: timestamp UTC
- `original_row_id`: reference id
