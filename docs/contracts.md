# Contracts (single source of truth; change only by stating the change)

## Conventions
- Timestamps: UTC, timezone-aware, microsecond precision (Polars Datetime("us","UTC")).
- Currency: INR. USD rows converted with fx_usd_inr in configs/base.yaml.
- series_id = ProviderName + "/" + ServiceName. Providers: aws_like, azure_like. Services: compute, database, object_storage, warehouse, cdn_egress, kubernetes (12 series).
- Splits by fraction of the time range, defined once in utils/splits.py: train 0.667, calibration 0.167, test 0.166. Boundaries: train [t0,t1), calib [t1,t2), test [t2,t3].
- Scales (configs/scale.yaml):
  tiny:  21 days,  2 providers, 6 services, 1 resource per service, 1 incident per fault type
  small: 90 days,  2 providers, 6 services, 2 resources per service
  full:  365 days, 2 providers, 6 services, 4 resources per service (~420k raw rows)
- Fault types: deployment_regression, autoscaling_runaway, traffic_surge, storage_leak, instance_upsize, egress_spike (test split only).
- Decoys: sale, month_end, holiday_dip.

## Paths under <artifact_root>/<scale>/
raw/charges/<YYYY-MM>.parquet, raw/events.parquet, raw/ground_truth.parquet, raw/clean_truth.parquet, raw/dirt_log.parquet
silver/charges.parquet, silver/quarantine.parquet, silver/dq_report.md
gold/service_hour.parquet, gold/service_day.parquet
p4/forecasts.parquet, p4/results.json
p5/alarms.parquet, p5/results.json
p6/attribution.parquet, p6/results.json
p7/*.csv, p7/*.png
demo/*

## charges (raw and silver): one row per resource-hour-charge
x_row_id (int64 unique), x_ingest_ts (UTC), x_source_tz (str),
ChargePeriodStart, ChargePeriodEnd, BillingPeriodStart, BillingPeriodEnd,
ProviderName, SubAccountId, ServiceName, ServiceCategory, ResourceId, ResourceType, RegionId,
ChargeCategory (Usage|Credit|Refund|Purchase), ChargeClass, PricingCategory (On-Demand|Committed),
ConsumedQuantity, ConsumedUnit, PricingQuantity, BillingCurrency,
ListCost, ContractedCost, BilledCost, EffectiveCost, Tags,
x_cpu_pct, x_mem_pct, x_requests, x_storage_gb, x_egress_gb, x_instance_count
Invariant on clean Usage rows: ListCost >= ContractedCost >= EffectiveCost. Credit and Refund rows have negative cost.

## events
ts, event_type (deployment|config_change|sale|month_end|holiday|price_change), series_id (nullable), meta (json string)

## ground_truth
incident_id, start, end, series_id, root_cause, propagated_series (list), magnitude_inr, is_decoy, is_overlap, is_confounded
magnitude_inr = total extra cost over [start,end) versus the no-fault world, computed by rerunning the world without the fault.

## dirt_log
x_row_id, dirt_type, original_value, corrupted_value
dirt_type values: missing_hours, duplicates, restatement, timezone_shift, unit_mix, null_resource_id, cpu_glitch, column_rename, tag_noise, currency_mix

## gold/service_hour: one row per (series_id, ts)
series_id, provider, service, ts, cost_inr, credits_inr, requests, cpu_pct, cpu_per_request, instance_count, storage_gb, egress_gb, egress_per_request, unit_price, n_resources_expected, n_resources_reported, is_complete, split
cost_inr = sum of EffectiveCost over Usage rows only; NaN when is_complete is False. Credits/refunds go to credits_inr. Cost is never imputed. Downstream skips incomplete hours.

## p4/forecasts
series_id, ts, y, yhat, lo, hi, model, split, horizon_h

## p5/alarms
alarm_id, series_id, detector, start, end

## p6/attribution
incident_key, series_id, method, rank, candidate_cause, effect_inr, ci_lo, ci_hi, score, low_confidence

## Function signatures
sim.build.build_dataset(scale: str, cfg: dict, out_dir: Path) -> dict[str, Path]
data.clean.run_cleaning(raw_dir: Path, out_dir: Path, cfg: dict) -> dict
data.features.build_gold(silver_dir: Path, out_dir: Path, cfg: dict) -> dict
forecast.gbm.fit_predict(gold: pl.DataFrame, cfg: dict) -> pl.DataFrame
forecast.conformal.calibrate(fc: pl.DataFrame, alpha: float, cfg: dict) -> pl.DataFrame
detect.conformal_detector.detect(fc: pl.DataFrame, k: int) -> pl.DataFrame
detect.eval.match_events(alarms, ground_truth, tol_hours: int) -> dict
attribute.control.synthetic_control(...) -> dict
utils.summary.print_result_summary(d: dict) -> None
