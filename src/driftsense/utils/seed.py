"""Randomness management to ensure end-to-end reproducibility."""

import os
import random
from typing import Optional

import numpy as np


def set_seed(seed: int = 42) -> int:
    """Seed Python random, NumPy, and environment variables.

    Parameters
    ----------
    seed : int
        Seed value to initialize generators.

    Returns
    -------
    int
        The seed that was set.
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    return seed
