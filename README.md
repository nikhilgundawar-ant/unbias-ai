# unbias-ai

**Your tone shouldn't change the facts.** Pre-alpha: test how much a Claude system prompt gives way under pressure (authority claims, insistence, emotion, repeated pushback) on matched question variants.

> Status: dev-only. No improvement claims yet. See `PLAN.md` and `evals/PROTOCOL.md`. Prior art: Dubois et al., *Ask don't tell* (arXiv:2602.23971) shows input reframing reduces sycophancy; this project credits and compares against it rather than claiming the idea.

## Install

Prerequisite: Claude Code installed and logged in (`claude auth status`), since `unbias` calls it headlessly.

```bash
pip install .            # or: uv tool install .
unbias --help
```

Uses headless Claude Code (`claude -p`) under your existing Claude login. No API key is needed. Reported costs are CLI usage estimates.

## Use

```bash
# Try it with no login and no calls (SIMULATED, scripted replies)
unbias pressure-test --demo

# Test your system prompt (calls Claude; budget-capped)
unbias pressure-test --system-prompt my_prompt.md --budget-usd 2

# Re-report a saved run offline (zero model calls)
unbias pressure-test --replay evals/runs/<run-dir>
```

The report shows collection, errors, and cost per variant kind, plus deterministic checks where an exact answer exists. It shows no AI-graded scores until the grader is calibrated.

## Develop

```bash
uv sync --group dev
uv run pytest
```

macOS note: uv's editable install writes a `.pth` file that macOS marks hidden, and recent Python skips hidden `.pth` files. Tests set `pythonpath = ["src"]`; for ad-hoc scripts use `PYTHONPATH=src uv run python …`. Installed (non-editable) wheels are unaffected.

License: Apache-2.0.
