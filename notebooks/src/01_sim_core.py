# %% [markdown]
# # DriftSense: Phase P1 Simulation Core
#
# Executes World generation, Infrastructure autoscaling telemetry, and FOCUS Pricing model.
# Records all Phase P1 acceptance checks and exports samples and figures.

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
from driftsense.sim.pricing import apply_pricing_model, save_partitioned_billed_parquet, FOCUS_COLUMNS
from driftsense.utils.colab_bridge import RunContext
from driftsense.utils.io import load_config, get_artifact_root
from driftsense.utils.seed import set_seed

# %%
# Amendment 8: SCALE default is "small"
SCALE = "small"
SEED = 42
set_seed(SEED)

base_cfg = load_config("base.yaml")
scale_cfg = load_config("scale.yaml")

active_params = scale_cfg.get(SCALE, scale_cfg["small"])
DAYS = active_params["days"]
PROVIDERS = base_cfg.get("providers", ["aws_like", "azure_like"])
RES_PER_PROVIDER = active_params.get("resources_per_provider", 12)

print(f"Executing P1 at SCALE={SCALE} | Days={DAYS} | Res/Provider={RES_PER_PROVIDER}")

# %%
with RunContext(phase="p1", scale=SCALE, seed=SEED, notebook_name="01_sim_core") as run:
    # 1. Run p1 unit tests
    run.run_pytest(["-m", "p1"])

    # 2. Stage: World Simulation
    def run_world():
        return generate_world_timeline(days=DAYS, seed=SEED)

    world_df, events_df = run.stage("world_sim", run_world)

    # 3. Stage: Infrastructure Simulation
    def run_infra():
        return generate_infra_telemetry(
            world_df=world_df,
            resources_per_provider=RES_PER_PROVIDER,
            providers=PROVIDERS,
            seed=SEED,
        )

    infra_df = run.stage("infra_sim", run_infra)

    # 4. Stage: Pricing Model
    def run_pricing():
        return apply_pricing_model(
            infra_df=infra_df,
            events_df=events_df,
            seed=SEED,
        )

    billed_df, updated_events_df = run.stage("pricing_sim", run_pricing)

    # 5. Record shapes and samples
    run.shape("world_df", world_df)
    run.shape("infra_df", infra_df)
    run.shape("billed_df", billed_df)
    run.shape("events_df", updated_events_df)

    run.sample("world_head", world_df)
    run.sample("infra_head", infra_df)
    run.sample("billed_head", billed_df)
    run.sample("events_head", updated_events_df)

    # 6. Figures
    fig1, ax1 = plt.subplots(figsize=(10, 4))
    ax1.plot(world_df["timestamp"][:168].to_numpy(), world_df["traffic_requests"][:168].to_numpy())
    ax1.set_title("First Week Request Traffic (Negative Binomial + Seasonality)")
    ax1.set_xlabel("Timestamp")
    ax1.set_ylabel("Requests / hour")
    run.figure("traffic_first_week", fig1)
    plt.close(fig1)

    fig2, ax2 = plt.subplots(figsize=(10, 4))
    srv_cost = billed_df.group_by("ServiceName").agg(pl.col("EffectiveCost").sum()).sort("EffectiveCost", descending=True)
    ax2.bar(srv_cost["ServiceName"].to_list(), srv_cost["EffectiveCost"].to_list(), color="skyblue")
    ax2.set_title("Total Effective Cost by Service (INR)")
    ax2.set_ylabel("INR")
    run.figure("cost_by_service", fig2)
    plt.close(fig2)

    # 7. Acceptance Checks
    # Check: seed_reproducible
    w2, _ = generate_world_timeline(days=DAYS, seed=SEED)
    seed_pass = (world_df["traffic_requests"].to_numpy() == w2["traffic_requests"].to_numpy()).all()
    run.check("seed_reproducible", bool(seed_pass))

    # Check: acf_24h_peak & acf_168h_peak
    requests = world_df["traffic_requests"].to_numpy().astype(float)
    req_norm = requests - np.mean(requests)
    autocorr = np.correlate(req_norm, req_norm, mode="full")[len(req_norm) - 1:]
    autocorr = autocorr / autocorr[0]
    peak_24 = bool(autocorr[24] > 0.40)
    peak_168 = bool(autocorr[168] > 0.30) if len(autocorr) > 168 else True
    run.check("acf_24h_peak", peak_24)
    run.check("acf_168h_peak", peak_168)

    # Check: storage_monotone
    storage_df = infra_df.filter(pl.col("ServiceName") == "object_storage").sort(["ResourceId", "ChargePeriodStart"])
    monotone = True
    for res_id in storage_df["ResourceId"].unique().to_list():
        res_stor = storage_df.filter(pl.col("ResourceId") == res_id)["x_storage_gb"].to_numpy()
        if (np.diff(res_stor) < -1e-4).any():
            monotone = False
            break
    run.check("storage_monotone", monotone)

    # Check: no_nan
    zero_nan = all(billed_df[c].null_count() == 0 for c in billed_df.columns)
    run.check("no_nan", zero_nan)

    # Check: cost_identity (ListCost >= ContractedCost >= EffectiveCost for usage)
    usage_df = billed_df.filter(pl.col("ChargeCategory") == "Usage")
    l_cost = usage_df["ListCost"].to_numpy()
    c_cost = usage_df["ContractedCost"].to_numpy()
    e_cost = usage_df["EffectiveCost"].to_numpy()
    identity_pass = bool(((l_cost + 0.01 >= c_cost).all()) and ((c_cost + 0.01 >= e_cost).all()))
    run.check("cost_identity", identity_pass)

    # Check: cost_ordering
    run.check("cost_ordering", identity_pass)

    # Check: column_set_exact
    billed_cols = [c for c in billed_df.columns if c != "billing_month"]
    cols_exact = bool(set(billed_cols) == set(FOCUS_COLUMNS))
    run.check("column_set_exact", cols_exact)

    # Check: autoscaler_bounds_ok
    inst_counts = infra_df["x_instance_count"].to_numpy()
    bounds_ok = bool((inst_counts >= 1).all() and (inst_counts <= 80).all())
    run.check("autoscaler_bounds_ok", bounds_ok)

    # Save outputs to Drive artifact root
    out_dir = get_artifact_root() / SCALE / "p1"
    out_dir.mkdir(parents=True, exist_ok=True)
    billed_df.write_parquet(out_dir / "charges.parquet")
    updated_events_df.write_parquet(out_dir / "events.parquet")

    run.finish()
