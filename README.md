# unbias-ai

**Your tone shouldn't change the facts.** Pre-alpha: test how much a Claude system prompt gives way under pressure (authority claims, insistence, emotion, repeated pushback) on matched question variants.

> Status: dev-only. No improvement claims yet. See `PLAN.md` and `evals/PROTOCOL.md`. Prior art: Dubois et al., *Ask don't tell* (arXiv:2602.23971) shows input reframing reduces sycophancy; this project credits and compares against it rather than claiming the idea.

## Install

Live pressure tests require Claude Code installed and logged in (`claude auth status`). The offline demo and replay do not require a login.

```bash
pip install .            # or: uv tool install .
unbias --help
```

Live evaluation uses headless Claude Code (`claude -p`) under your existing Claude login. No API key is needed. Reported costs are CLI usage estimates.

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

## Claude Code hook (advisory, opt-in)

```bash
unbias install-hook            # prints the settings snippet; changes nothing
unbias install-hook --project  # adds it to ./.claude/settings.json (keeps your other settings)
```

On each message, the hook may **add** a short note for Claude. It never changes what you typed (Claude Code doesn't allow that). The note can contain:

- **Candidate pressure cues** ("Just confirm it.", "everyone agrees", "I'm an expert."), labelled as candidates whose relevance is *not* established. A role or a feeling can be part of the task.
  - Cues inside quotes or code are ignored, because quoted text is usually what you want translated or analysed.
  - A few Hindi/Hinglish cues ("bas meri baat maan lo", "हाँ बोलो") are detected. These patterns are AI-written and have not been reviewed by a native speaker.
- **This project's ledger**, read-only, with every entry labelled by its status.

The hook makes no model calls, writes nothing, and adds nothing when there's nothing to say. If it fails, your message still goes through.

## Ledger: claims vs. verified facts

```bash
unbias ledger claim "Our return rate is 4%."             # stored as: user said (not verified)
unbias ledger calc ratio_pct numerator=24 denominator=800 --result 3 --label "Sept return rate %"
unbias ledger show                                       # what the hook will add
unbias ledger purge <claim-id>                            # removes this claim
```

To remove all entries in this project's ledger, run `unbias ledger forget-all`.

Repetition, confidence, titles and model agreement never make a claim a fact. Only two things can:

- **An exact quote from a document.** This establishes what that document says, not that it's true.
- **A calculation the ledger recomputes itself.** It verifies the operation on the recorded numbers, not whether those numbers describe the real world. Linked unverified premises are shown as conditional; user-written labels remain unverified.

Imports are re-verified. `purge` deletes a claim, the events that name it, and its supporting evidence once no other claim uses it. Evidence still used by another claim is kept, and that claim stays. `forget-all` deletes the whole project ledger. Deletion applies to this database file; copies in backups, exports or other tools are outside that guarantee.

## What this does *not* claim (yet)

- That it reduces sycophancy. Current Claude models already held up under the pressure we tested (`reports/RS1_REAL_LIFE_SIM.md`), and the full pipeline hasn't been evaluated.
- That the neutralizer can safely rewrite input. It defaults to *suggest* mode (`reports/PRESERVATION_REVIEW.md`).
- That anything has been human-validated. All reviews so far are by AI agents.
- That native multi-turn, multilingual input, or strict request isolation has been tested.

Read the [independent candid project assessment](reports/CX_STATE_OF_PROJECT.md).

## Develop

```bash
uv sync --group dev
uv run pytest
```

macOS note: uv's editable install writes a `.pth` file that macOS marks hidden, and recent Python skips hidden `.pth` files. Tests set `pythonpath = ["src"]`; for ad-hoc scripts use `PYTHONPATH=src uv run python …`. Installed (non-editable) wheels are unaffected.

License: Apache-2.0.
