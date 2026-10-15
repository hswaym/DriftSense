Fix the failures from the last review for the phase and scale I give you.
1. Read docs/reviews/<phase>-<scale>.md and runs/<scale>/<phase>/.
2. State the root cause in two sentences with evidence from the run report.
3. Write a regression test (marked @pytest.mark.<phase>) that would have caught it. It runs in Colab, not locally.
4. Fix the cause in src/. Do not weaken tests, assertions, thresholds, or docs/acceptance.yaml. If a threshold looks wrong, stop and ask me.
5. Search src/ for the same bug pattern and fix other occurrences.
6. Run only: ruff check, python -m compileall src, python tools/build_notebooks.py.
7. If docs/contracts.md must change, say exactly what and why, then update it.
8. Commit, push. Then tell me: run notebooks/colab/99_debug with PYTEST_ARGS set to the new test, then rerun the phase notebook.
