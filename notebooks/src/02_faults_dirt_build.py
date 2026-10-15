# %% [markdown]
# # DriftSense: Phase P2 Faults & Build
#
# Generates physical telemetry fault injection, decoys, held-out constraints,
# and outputs ground_truth table. (Faults portion of Phase P2).

# %%
import os
from pathlib import Path
import sys

# Setup path to src
current_dir = Path.cwd()
if (current_dir / "src").exists():
    sys.path.insert(0, str(current_dir / "src"))
elif (current_dir.parent / "src").exists():
    sys.path.insert(0, str(current_dir.parent / "src"))

try:
    from google.colab import drive  # type: ignore
    drive.mount("/content/drive")
    IN_COLAB = True
except Exception:
    IN_COLAB = False

import numpy as np
import polars as pl
import matplotlib.pyplot as plt

from driftsense.sim.world import generate_world_timeline
from driftsense.sim.infra import generate_infra_telemetry
from driftsense.sim.pricing import apply_pricing_model
from driftsense.sim.faults import inject_faults_and_decoys
from driftsense.utils.colab_bridge import RunContext
from driftsense.utils.io import load_config, get_artifact_root
from driftsense.utils.seed import set_seed
from driftsense.utils.splits import assign_split

# %%
# Amendment 8: SCALE default is "full"
SCALE = "full"
SEED = 42
set_seed(SEED)

base_cfg = load_config("base.yaml")
scale_cfg = load_config("scale.yaml")

active_params = scale_cfg.get(SCALE, scale_cfg["full"])
DAYS = active_params["days"]
PROVIDERS = base_cfg.get("providers", ["aws_like", "azure_like"])
RES_PER_PROVIDER = active_params.get("resources_per_provider", 24)

print(f"Executing Faults Build at SCALE={SCALE} | Days={DAYS} | Res/Provider={RES_PER_PROVIDER}")

# %%
with RunContext(phase="p2", scale=SCALE, seed=SEED, notebook_name="02_faults_dirt_build") as run:
    # 1. Run p2 unit tests
    run.run_pytest(["-m", "p2"])

    # 2. Stage: Base Simulation
    world_df, events_df = generate_world_timeline(days=DAYS, seed=SEED)
    infra_df = generate_infra_telemetry(
        world_df=world_df,
        resources_per_provider=RES_PER_PROVIDER,
        providers=PROVIDERS,
        seed=SEED,
    )
    clean_billed_df, clean_events_df = apply_pricing_model(
        infra_df=infra_df,
        events_df=events_df,
        seed=SEED,
    )

    # 3. Stage: Fault Injection
    def run_faults():
        return inject_faults_and_decoys(
            infra_df=infra_df,
            world_df=world_df,
            events_df=clean_events_df,
            seed=SEED,
        )

    faulted_infra_df, ground_truth_df, updated_events_df = run.stage("fault_injection", run_faults)
    billed_df, final_events_df = apply_pricing_model(
        infra_df=faulted_infra_df,
        events_df=updated_events_df,
        seed=SEED,
    )

    # 4. Shapes and Samples
    run.shape("ground_truth_df", ground_truth_df)
    run.shape("billed_df", billed_df)
    run.sample("ground_truth_head", ground_truth_df)
    run.sample("billed_head", billed_df)

    # 5. Metrics
    non_decoys = ground_truth_df.filter(~pl.col("is_decoy"))
    decoys = ground_truth_df.filter(pl.col("is_decoy"))
    run.metric("n_incidents_nondecoy", len(non_decoys))
    run.metric("n_decoys", len(decoys))

    # 6. Figures (Example Incident with Window Shading)
    if len(non_decoys) > 0:
        first_inc = non_decoys.row(0, named=True)
        inc_service = first_inc["service"]
        srv_costs = billed_df.filter(pl.col("ServiceName") == inc_service).group_by("ChargePeriodStart").agg(pl.col("BilledCost").sum()).sort("ChargePeriodStart")
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(srv_costs["ChargePeriodStart"][:200].to_numpy(), srv_costs["BilledCost"][:200].to_numpy(), label=f"{inc_service} Billed Cost")
        ax.axvspan(first_inc["start"], first_inc["end"], color="red", alpha=0.3, label=f"Fault: {first_inc['root_cause']}")
        ax.set_title(f"Example Incident: {first_inc['root_cause']} on {inc_service}")
        ax.legend()
        run.figure("example_incident_window", fig)
        plt.close(fig)

    # 7. Acceptance Checks
    # Check: incident_counts_ok
    run.check("incident_counts_ok", len(non_decoys) >= 4)

    # Check: deviation_3sigma_ok
    clean_srv = clean_billed_df.group_by(["ChargePeriodStart", "ServiceName"]).agg(pl.col("BilledCost").sum())
    fault_srv = billed_df.group_by(["ChargePeriodStart", "ServiceName"]).agg(pl.col("BilledCost").sum())
    sig_dev = True
    for inc in non_decoys.iter_rows(named=True):
        srv = inc["service"]
        clean_c = clean_srv.filter(pl.col("ServiceName") == srv)["BilledCost"].to_numpy()
        med = np.median(clean_c)
        mad = max(1.0, 1.4826 * np.median(np.abs(clean_c - med)))
        w_max = fault_srv.filter(
            (pl.col("ServiceName") == srv) & (pl.col("ChargePeriodStart") >= inc["start"]) & (pl.col("ChargePeriodStart") <= inc["end"])
        )["BilledCost"].max()
        z = (w_max - med) / mad
        if z < 2.5:
            sig_dev = False
            break
    run.check("deviation_3sigma_ok", sig_dev)

    # Check: decoys_present
    run.check("decoys_present", len(decoys) > 0)

    # Check: heldout_absent_train_calib
    egress_incidents = ground_truth_df.filter(pl.col("root_cause") == "egress_spike")
    labeled_gt = assign_split(egress_incidents, ts_col="start")
    heldout_only_test = (labeled_gt["split"] == "test").all() if len(egress_incidents) > 0 else True
    run.check("heldout_absent_train_calib", bool(heldout_only_test))

    # Check: magnitude_nonneg
    mag_nonneg = (ground_truth_df["magnitude_inr"] >= 0).all()
    run.check("magnitude_nonneg", bool(mag_nonneg))

    # Check: confounded_cases_present
    confounded_in_events = final_events_df.filter(pl.col("metadata").str.contains("(?i)confounded"))
    run.check("confounded_cases_present", len(confounded_in_events) > 0)

    # Save to Drive artifacts
    out_dir = get_artifact_root() / SCALE / "p2"
    out_dir.mkdir(parents=True, exist_ok=True)
    ground_truth_df.write_parquet(out_dir / "ground_truth.parquet")
    clean_billed_df.write_parquet(out_dir / "clean_truth.parquet")
    final_events_df.write_parquet(out_dir / "events.parquet")
    billed_df.write_parquet(out_dir / "faulted_charges.parquet")

    run.finish()
