"""Compiler from percent-format Python scripts to Jupyter notebooks.

Converts notebooks/src/<name>.py -> notebooks/colab/<name>.ipynb.
Guarantees byte-identical deterministic JSON output by enforcing fixed cell IDs,
consistent metadata, and zero execution counts.
"""

import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List

import nbformat


def py_percent_to_notebook(py_content: str) -> nbformat.NotebookNode:
    """Parse a percent-format Python string into an nbformat NotebookNode.

    Cells are split on lines starting with '# %%'.
    If the delimiter is '# %% [markdown]', it becomes a markdown cell.
    """
    lines = py_content.splitlines()
    raw_cells: List[Dict[str, Any]] = []
    current_cell_type = "code"
    current_lines: List[str] = []

    for line in lines:
        if line.startswith("# %%"):
            if current_lines or raw_cells:
                raw_cells.append({"type": current_cell_type, "lines": current_lines})
                current_lines = []
            if "[markdown]" in line:
                current_cell_type = "markdown"
            else:
                current_cell_type = "code"
        else:
            current_lines.append(line)

    if current_lines or not raw_cells:
        raw_cells.append({"type": current_cell_type, "lines": current_lines})

    nb_cells = []
    cell_idx = 0

    for raw in raw_cells:
        cell_type = raw["type"]
        cell_lines = raw["lines"]

        # Drop leading/trailing empty lines per cell
        while cell_lines and cell_lines[0].strip() == "":
            cell_lines.pop(0)
        while cell_lines and cell_lines[-1].strip() == "":
            cell_lines.pop()

        if cell_type == "markdown":
            clean_lines = []
            for cl in cell_lines:
                if cl.startswith("# "):
                    clean_lines.append(cl[2:] + "\n")
                elif cl == "#":
                    clean_lines.append("\n")
                else:
                    clean_lines.append(cl + "\n")
            source_str = "".join(clean_lines).rstrip() + "\n" if clean_lines else ""
            cell = nbformat.v4.new_markdown_cell(source=source_str)
        else:
            source_str = "\n".join(cell_lines) + "\n" if cell_lines else ""
            cell = nbformat.v4.new_code_cell(source=source_str)
            cell.execution_count = None
            cell.outputs = []

        # Enforce deterministic cell id (avoids random UUIDs in nbformat >= 4.5)
        cell["id"] = f"cell-{cell_idx:03d}"
        cell_idx += 1
        nb_cells.append(cell)

    nb = nbformat.v4.new_notebook(cells=nb_cells)
    nb.metadata = {
        "language_info": {
            "name": "python"
        }
    }
    nb["nbformat"] = 4
    nb["nbformat_minor"] = 5

    # Validate against nbformat schema
    nbformat.validate(nb)
    return nb


def build_single_notebook(src_path: Path, dest_path: Path) -> None:
    """Compile a single percent script to .ipynb."""
    content = src_path.read_text(encoding="utf-8")
    nb = py_percent_to_notebook(content)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    # Write deterministic JSON
    json_str = json.dumps(nb, indent=1, ensure_ascii=False) + "\n"
    dest_path.write_text(json_str, encoding="utf-8", newline="\n")


def build_all_notebooks(
    src_dir: Path = Path("notebooks/src"),
    dest_dir: Path = Path("notebooks/colab"),
) -> List[Path]:
    """Compile all .py files in src_dir to dest_dir."""
    built = []
    if not src_dir.exists():
        return built

    for py_file in sorted(src_dir.glob("*.py")):
        nb_name = py_file.stem + ".ipynb"
        dest_file = dest_dir / nb_name
        build_single_notebook(py_file, dest_file)
        built.append(dest_file)
        print(f"[BUILT] {py_file} -> {dest_file}")

    return built


if __name__ == "__main__":
    src_d = Path("notebooks/src")
    dest_d = Path("notebooks/colab")
    built_paths = build_all_notebooks(src_d, dest_d)
    print(f"Successfully compiled {len(built_paths)} notebooks.")
    sys.exit(0)
