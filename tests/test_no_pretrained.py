"""Test enforcing strict zero-pretrained and zero-external-LLM invariant."""

from pathlib import Path
import pytest

pytestmark = pytest.mark.p0

FORBIDDEN_PATTERNS = [
    "from_pretrained",
    "transformers",
    "torch.hub",
    "anthropic",
    "openai",
    "chronos",
    "timesfm",
]


def test_no_pretrained_weights_or_llms():
    """Scan all Python files in src/ to ensure no pretrained model or external LLM API is used."""
    src_dir = Path(__file__).resolve().parent.parent / "src"
    assert src_dir.exists(), f"Source directory does not exist: {src_dir}"

    violations = []

    for py_file in src_dir.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception as e:
            pytest.fail(f"Could not read {py_file}: {e}")

        for pattern in FORBIDDEN_PATTERNS:
            if pattern in content:
                violations.append(f"Forbidden pattern '{pattern}' detected in {py_file}")

    assert not violations, "\n".join(violations)
