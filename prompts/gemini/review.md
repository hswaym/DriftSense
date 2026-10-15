Review the Colab run for the phase and scale I give you.
1. Run: python tools/pull_runs.py
2. Run: python tools/verify_run.py <phase> --scale <scale> and quote the full output.
3. Read runs/<scale>/<phase>/summary.json, checks.json, pytest.txt, stdout.log (tail), error.txt if present, samples/*.csv, and view figures/*.png.
4. Compare with docs/acceptance.yaml and docs/traps.md.
5. Apply suspicious_rules. Treat too-good results as likely bugs; name the likely leak or bug and the file to inspect.
6. Do not invent numbers. Do not run training, pipelines, or pytest locally.
7. Output the Review format from GEMINI.md and save it to docs/reviews/<phase>-<scale>.md.
End with exactly one line: NEXT: <what I should do now>.
