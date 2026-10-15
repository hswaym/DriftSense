# Design traps (agents fall into these)
1. Forecast horizon is 24 hours ahead. Features only from t-24h or earlier. Lag-1 features let the model follow the anomaly and residuals vanish. Allowed: calendar features known in advance (hour_of_week, holiday, sale, month_end). Not allowed: deployments or telemetry at time t.
2. Attribution controls = series with no alarm in the incident window (from detection output). Never choose controls from ground_truth.
3. Conformal quantile: k = ceil((n+1)*(1-alpha)), k-th smallest calibration score; if k > n the interval is infinite. Calibrate per series. Calibration residuals come from a model trained on the train split only.
4. Missing hours: gold marks is_complete=False and cost_inr=NaN. Never fill cost. Detectors and forecasters skip incomplete hours, else missing rows look like false cost dips.
5. Restatements need x_ingest_ts: latest ingest wins per key.
6. Timezone shift: dirt shifts aws_like timestamps and records x_source_tz; cleaning converts back using that column.
7. Schema drift: dirt renames a column on azure_like in later monthly files only; cleaning applies a rename map per file.
8. Rolling features use data shifted by 24h before the window. Leakage test perturbs the future and checks features at t are unchanged.
9. Confounded case: a deployment event with NO real effect plus a real traffic_surge on the same day. True root cause = traffic_surge. Correlation on event flags blames the deployment.
10. egress_spike appears only in the test split. Nothing is tuned or fit on it.
11. Event matching: an alarm is a hit if it starts in [start - tol_hours, end]. One alarm matches at most one incident. Unmatched alarms are false positives. Alarms on decoys are counted separately as decoy false alarms.
12. Validate silver and gold with pandera at every read and write boundary.
13. magnitude_inr comes from a no-fault world rerun, not from noisy data.
14. Never read ground_truth in modeling, detection, or attribution code; only in evaluation code.
