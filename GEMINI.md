# DriftSense: Gemini CLI context
Role: reviewer and fixer of Colab run outputs.
First read AGENTS.md, docs/contracts.md, docs/acceptance.yaml, docs/traps.md.
Execution rule: never run training, dataset builds, simulations, or pytest locally. Allowed locally: git, ruff check, python -m compileall src, python tools/build_notebooks.py, python tools/verify_run.py, python tools/pull_runs.py.
Run reports live in runs/<scale>/<phase>/ (pulled from branch colab-runs): summary.json, checks.json, stdout.log, pytest.txt, error.txt, env.txt, samples/, figures/.
Review rules:
- Run python tools/pull_runs.py then python tools/verify_run.py <phase> --scale <scale>. Quote its output.
- Never say a phase passes without quoting check lines and metric values from the run report.
- Never invent numbers. Use only values in the run report.
- Apply suspicious_rules in docs/acceptance.yaml. Treat too-good results as bugs until explained.
- If error.txt exists, diagnose it first.
Fix rules:
- Root cause in two sentences with evidence.
- Add a regression test first (runs in Colab). Then fix the cause.
- Never weaken tests, assertions, thresholds, or acceptance.yaml. If a threshold looks wrong, stop and ask.
- Never change docs/contracts.md silently.
- No pretrained models or external APIs.
- git pull before editing. Small commits. Push. Tell the user which Colab notebook to rerun.
Review output format:
VERDICT: PASS | PASS_WITH_WARNINGS | FAIL
CHECKS: table from verify_run
SUSPICIOUS: rule id + evidence quote, or none
ROOT CAUSES (if FAIL): ranked, with evidence
NEXT: exact commands / notebook to rerun
Save the review to docs/reviews/<phase>-<scale>.md.
