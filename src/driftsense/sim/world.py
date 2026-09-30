"""World simulation module: simulates realistic traffic, seasonality, Indian calendar events, and deployments.

Design Rationale:
- Real-world cloud workloads exhibit strong multi-scale periodicities: diurnal (24-hour),
  weekly (168-hour), and annual trends.
- Web request traffic uses a Negative Binomial distribution rather than Poisson because
  real request arrivals exhibit overdispersion (clustering, variance > mean).
- Indian holiday, sales (e.g. Diwali, Independence Day, Republic Day sales), and
  month-end accounting close events create legitimate, non-fault traffic surges.
- Deployments are simulated as a Poisson process during standard working hours (10:00 to 18:00),
  reflecting enterprise CI/CD release cadences.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import polars as pl

from driftsense.utils.seed import set_seed


@dataclass(frozen=True)
class CalendarEvent:
    name: str
    event_type: str
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    traffic_multiplier: float
    description: str


# Canonical Indian national holidays and major shopping festival periods (2024 calendar)
INDIAN_CALENDAR_EVENTS: List[CalendarEvent] = [
    CalendarEvent("Republic Day Sale", "sale", "2024-01-20", "2024-01-26", 1.85, "Republic Day mega sale"),
    CalendarEvent("Holi Festival", "holiday", "2024-03-24", "2024-03-26", 0.70, "Holi holiday weekend dip"),
    CalendarEvent("Summer Freedom Sale", "sale", "2024-05-03", "2024-05-07", 1.50, "Mid-year consumer electronics sale"),
    CalendarEvent("Independence Day Sale", "sale", "2024-08-09", "2024-08-15", 2.10, "Great Freedom / Independence sale"),
    CalendarEvent("Gandhi Jayanti", "holiday", "2024-10-02", "2024-10-02", 0.75, "National holiday traffic reduction"),
    CalendarEvent("Dussehra Festival", "holiday", "2024-10-11", "2024-10-13", 0.85, "Festive holiday"),
    CalendarEvent("Diwali Festive Sale", "sale", "2024-10-25", "2024-11-03", 2.60, "Annual peak festive e-commerce sale"),
    CalendarEvent("Christmas & Year-End Sale", "sale", "2024-12-22", "2024-12-31", 1.95, "Year-end holiday rush"),
]


def generate_world_timeline(
    days: int = 14,
    start_date_str: str = "2024-01-01 00:00:00",
    base_rps: float = 1200.0,
    annual_growth_rate: float = 0.35,
    seed: int = 42,
) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """Generate hourly world environment timeline with multi-seasonality, calendar events, and deployments.

    Parameters
    ----------
    days : int
        Number of simulation days.
    start_date_str : str
        Start timestamp in format 'YYYY-MM-DD HH:MM:SS'.
    base_rps : float
        Baseline requests per second. Multiplied by 3600 to get hourly requests.
    annual_growth_rate : float
        Fractional business traffic growth across a 365-day year.
    seed : int
        Deterministic random seed.

    Returns
    -------
    Tuple[pl.DataFrame, pl.DataFrame]
        - world_df: Hourly timeline of requests, seasonality factors, and calendar flags.
        - events_df: Discrete event log for deployments, sales, and holidays.
    """
    set_seed(seed)
    rng = np.random.default_rng(seed)

    total_hours = days * 24
    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")

    # Timestamps (hourly sequence)
    timestamps = [start_dt + timedelta(hours=i) for i in range(total_hours)]
    hour_of_day = np.array([dt.hour for dt in timestamps], dtype=np.int32)
    day_of_week = np.array([dt.weekday() for dt in timestamps], dtype=np.int32) # 0=Mon, 6=Sun
    day_of_year = np.array([dt.timetuple().tm_yday for dt in timestamps], dtype=np.int32)

    # 1. Long-term trend: compound growth over the year
    # t_fraction from 0.0 to days / 365.0
    t_fraction = np.arange(total_hours, dtype=np.float64) / (365.0 * 24.0)
    trend = 1.0 + (annual_growth_rate * t_fraction)

    # 2. Diurnal (24-hour) seasonality
    # Realistic Indian internet traffic: low trough at 04:00 (0.35), morning ramp 10:00 (1.1),
    # afternoon plateau, evening prime-time peak at 20:00-22:00 (1.55).
    # Parameterized via two Fourier harmonics for smooth natural curvature
    h_rad = 2.0 * np.pi * (hour_of_day - 4) / 24.0
    daily_seasonality = (
        1.0
        - 0.50 * np.cos(h_rad)
        - 0.15 * np.cos(2 * h_rad)
        + 0.10 * np.sin(h_rad)
    )
    daily_seasonality = np.maximum(0.25, daily_seasonality)

    # 3. Weekly (168-hour) seasonality
    # Weekdays (Mon-Fri) elevated enterprise / general traffic (~1.0 - 1.05),
    # Saturday slight dip (~0.90), Sunday evening rebound (~0.95).
    weekday_weights = np.array([1.02, 1.04, 1.05, 1.03, 1.00, 0.88, 0.94], dtype=np.float64)
    weekly_seasonality = weekday_weights[day_of_week]

    # 4. Indian Calendar Multipliers (Holidays, Sales, Month-End Batches)
    calendar_mult = np.ones(total_hours, dtype=np.float64)
    is_holiday = np.zeros(total_hours, dtype=bool)
    is_sale_event = np.zeros(total_hours, dtype=bool)
    is_month_end = np.zeros(total_hours, dtype=bool)

    events_records: List[Dict] = []

    for event in INDIAN_CALENDAR_EVENTS:
        ev_start = datetime.strptime(f"{event.start_date} 00:00:00", "%Y-%m-%d %H:%M:%S")
        ev_end = datetime.strptime(f"{event.end_date} 23:59:59", "%Y-%m-%d %H:%M:%S")

        # Mask within window
        for idx, dt in enumerate(timestamps):
            if ev_start <= dt <= ev_end:
                calendar_mult[idx] *= event.traffic_multiplier
                if event.event_type == "holiday":
                    is_holiday[idx] = True
                elif event.event_type == "sale":
                    is_sale_event[idx] = True

        # Log event if it intersects our simulation window
        if ev_start <= timestamps[-1] and ev_end >= timestamps[0]:
            events_records.append({
                "timestamp": ev_start,
                "event_type": event.event_type,
                "service": "all",
                "metadata": f"{event.name}: {event.description} (mult: {event.traffic_multiplier})"
            })

    # Month-end batch indicator (last 2 days of each calendar month)
    for idx, dt in enumerate(timestamps):
        next_day = dt + timedelta(days=2)
        if next_day.month != dt.month:
            is_month_end[idx] = True
            calendar_mult[idx] *= 1.15 # 15% batch billing & closing queries

    # 5. Composite expected hourly request mean
    hourly_base = base_rps * 3600.0
    expected_requests = hourly_base * trend * daily_seasonality * weekly_seasonality * calendar_mult

    # 6. Negative Binomial Stochastic Noise
    # Mean mu = expected_requests. Dispersion parameter alpha determines variance:
    # Var = mu + alpha * mu^2. We choose alpha = 0.008 (realistic 10-15% CV at scale).
    # Converting to standard scipy/numpy (n, p) parametrization:
    # p = 1 / (1 + alpha * mu), n = 1 / alpha = mu * p / (1 - p)
    alpha = 0.008
    n_param = 1.0 / alpha
    p_param = 1.0 / (1.0 + alpha * expected_requests)
    
    # Vectorized negative binomial generation
    traffic_requests = rng.negative_binomial(n=n_param, p=p_param).astype(np.int64)

    # 7. CI/CD Deployments: Poisson process during working hours (Mon-Fri 10:00 - 18:00)
    is_work_hour = (day_of_week < 5) & (hour_of_day >= 10) & (hour_of_day < 18) & (~is_holiday)
    deploy_lambda = np.where(is_work_hour, 0.22, 0.0) # ~1.7 deployments per working day
    deployments = rng.poisson(lam=deploy_lambda).astype(np.int32)

    # Log deployments into events
    for idx, dep_count in enumerate(deployments):
        if dep_count > 0:
            for d in range(dep_count):
                events_records.append({
                    "timestamp": timestamps[idx],
                    "event_type": "deployment",
                    "service": "compute",
                    "metadata": f"CI/CD release build #{idx:04d}-{d+1}"
                })

    world_df = pl.DataFrame({
        "timestamp": timestamps,
        "hour_of_day": hour_of_day,
        "day_of_week": day_of_week,
        "day_of_year": day_of_year,
        "trend_factor": trend,
        "daily_seasonality": daily_seasonality,
        "weekly_seasonality": weekly_seasonality,
        "calendar_mult": calendar_mult,
        "is_holiday": is_holiday,
        "is_sale_event": is_sale_event,
        "is_month_end": is_month_end,
        "expected_requests": expected_requests,
        "traffic_requests": traffic_requests,
        "deployments": deployments,
    })

    if events_records:
        events_df = pl.DataFrame(events_records).sort("timestamp")
    else:
        events_df = pl.DataFrame(
            schema={"timestamp": pl.Datetime, "event_type": pl.Utf8, "service": pl.Utf8, "metadata": pl.Utf8}
        )

    return world_df, events_df
