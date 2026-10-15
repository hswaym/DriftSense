"""Time-based split utilities.

Contracts definition:
- Splits by fraction of total time range:
    Train:       0.667
    Calibration: 0.167
    Test:        0.166
- Boundaries:
    Train:       [t0, t1)
    Calibration: [t1, t2)
    Test:        [t2, t3] (closed interval: includes the final timestamp t3)
"""

from datetime import datetime
from typing import Tuple, Union

import polars as pl

TRAIN_FRACTION = 0.667
CALIB_FRACTION = 0.167
TEST_FRACTION = 0.166


def get_split_boundaries(
    start_dt: datetime,
    end_dt: datetime,
) -> Tuple[datetime, datetime, datetime, datetime]:
    """Calculate timestamp boundaries for train, calibration, and test splits.

    Parameters
    ----------
    start_dt : datetime
        Initial timestamp (t0).
    end_dt : datetime
        Final timestamp (t3).

    Returns
    -------
    Tuple[datetime, datetime, datetime, datetime]
        (t0, t1, t2, t3) where:
        Train:       [t0, t1)
        Calibration: [t1, t2)
        Test:        [t2, t3]
    """
    if end_dt <= start_dt:
        raise ValueError(f"end_dt ({end_dt}) must be strictly after start_dt ({start_dt})")

    total_duration = end_dt - start_dt
    t0 = start_dt
    t1 = t0 + total_duration * TRAIN_FRACTION
    t2 = t1 + total_duration * CALIB_FRACTION
    t3 = end_dt

    return t0, t1, t2, t3


def assign_split(
    df: pl.DataFrame,
    ts_col: str = "ChargePeriodStart",
    split_col: str = "split",
) -> pl.DataFrame:
    """Assign split label ('train', 'calib', 'test') to each row based on timestamp.

    Interval conventions:
    - Train:       [t0, t1)
    - Calibration: [t1, t2)
    - Test:        [t2, t3] (closed, includes maximum timestamp t3)

    Parameters
    ----------
    df : pl.DataFrame
        Input DataFrame containing a datetime timestamp column.
    ts_col : str
        Name of timestamp column.
    split_col : str
        Name of split column to add.

    Returns
    -------
    pl.DataFrame
        DataFrame with added string split column.
    """
    if ts_col not in df.columns:
        raise KeyError(f"Timestamp column '{ts_col}' not found in DataFrame columns: {df.columns}")

    if df.height == 0:
        return df.with_columns(pl.lit(None, dtype=pl.Utf8).alias(split_col))

    min_ts: Union[datetime, None] = df[ts_col].min()
    max_ts: Union[datetime, None] = df[ts_col].max()

    if min_ts is None or max_ts is None:
        return df.with_columns(pl.lit("train").alias(split_col))

    if min_ts == max_ts:
        return df.with_columns(pl.lit("train").alias(split_col))

    t0, t1, t2, t3 = get_split_boundaries(min_ts, max_ts)

    # Polars expressions for partition:
    # Train: [t0, t1)
    # Calib: [t1, t2)
    # Test:  [t2, t3]
    split_expr = (
        pl.when(pl.col(ts_col) < t1)
        .then(pl.lit("train"))
        .when(pl.col(ts_col) < t2)
        .then(pl.lit("calib"))
        .otherwise(pl.lit("test"))
    )

    return df.with_columns(split_expr.alias(split_col))
