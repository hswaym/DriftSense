"""I/O and configuration loading utilities."""

import os
from pathlib import Path
from typing import Any, Dict

import yaml


def get_project_root() -> Path:
    """Return the absolute path to the project root directory.

    Searches upward from the current file until configs/base.yaml or pyproject.toml is found.
    """
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "configs" / "base.yaml").exists() or (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def load_config(config_name: str = "base.yaml", config_dir: str = "configs") -> Dict[str, Any]:
    """Load a YAML configuration file from the configs directory.

    Parameters
    ----------
    config_name : str
        Name of YAML file (e.g. 'base.yaml', 'scale.yaml').
    config_dir : str
        Relative or absolute path to configs folder.

    Returns
    -------
    Dict[str, Any]
        Parsed configuration dictionary.
    """
    if os.path.isabs(config_dir):
        path = Path(config_dir) / config_name
    else:
        path = get_project_root() / config_dir / config_name

    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config or {}
