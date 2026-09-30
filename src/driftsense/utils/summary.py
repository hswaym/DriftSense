"""RESULT SUMMARY generation for Colab-Antigravity audit loop."""

import json
from typing import Any, Dict


def format_result_summary(summary: Dict[str, Any]) -> str:
    """Format a result dictionary into the standardized DriftSense RESULT SUMMARY block.

    Parameters
    ----------
    summary : Dict[str, Any]
        Dictionary containing phase, scale, seed, runtime_sec, shapes, key_metrics,
        checks, warnings, and artifacts.

    Returns
    -------
    str
        Formatted RESULT SUMMARY string.
    """
    phase = summary.get("phase", "unknown")
    scale = summary.get("scale", "tiny")
    seed = summary.get("seed", 42)
    runtime_sec = summary.get("runtime_sec", 0.0)
    shapes = summary.get("shapes", {})
    key_metrics = summary.get("key_metrics", {})
    checks = summary.get("checks", {})
    warnings = summary.get("warnings", [])
    artifacts = summary.get("artifacts", [])

    lines = [
        "=== RESULT SUMMARY ===",
        f"phase: {phase}",
        f"scale: {scale}",
        f"seed: {seed}",
        f"runtime_sec: {runtime_sec:.2f}" if isinstance(runtime_sec, (int, float)) else f"runtime_sec: {runtime_sec}",
        f"shapes: {json.dumps(shapes)}",
        f"key_metrics: {json.dumps(key_metrics)}",
        f"checks: {json.dumps(checks)}",
        f"warnings: {json.dumps(warnings)}",
        f"artifacts: {json.dumps(artifacts)}",
        "======================",
    ]
    return "\n".join(lines)


def print_result_summary(summary: Dict[str, Any]) -> None:
    """Print the standardized RESULT SUMMARY block to stdout.

    Parameters
    ----------
    summary : Dict[str, Any]
        Dictionary conforming to the RESULT SUMMARY specification.
    """
    print(format_result_summary(summary))
