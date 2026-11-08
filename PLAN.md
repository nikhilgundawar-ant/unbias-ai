# unbias-ai — Build Plan (pre-build)

Status: draft v0.1, written by Claude Code. Open stack questions are in `COMMON_CONTEXT.md` (Codex advising).
Items tagged `[verify]` are from memory and must be checked against current docs/papers before we rely on them.

## 1. Problem and thesis

Sycophancy = the model shifts answers toward what the user seems to want (stated opinion, tone, identity, pushback) instead of what is true. Three leak paths:

1. **Input leak**: tone, framing, presuppositions, and stated beliefs in the question steer the answer.
2. **Context leak**: earlier turns (user opinions, model agreements) get re-used as if they were facts, so bias compounds.
3. **Output leak**: flattery, over-confident agreement, and training-prior opinions presented as settled.

Thesis: put a deterministic-where-possible pipeline around the model so that only **neutralized questions** and **evidence-backed facts** reach it, and the answer is returned in a **neutral, calibrated** form.

**Target (D7):** reduce changes in factual conclusions caused by irrelevant tone, flattery, hostility, authority claims, or pressure, while preserving task meaning, useful empathy, legitimate preferences, and responsiveness to evidence and valid reasoning. We never claim "completely unbiased".

Non-goals: not a truth oracle; not a jailbreak/safety filter; will not hide the user's original text from them. Honest limit: neutralizing the *prompt* cannot remove biases baked into the model's weights. We surface those (see §3.5) rather than claim to remove them.

## 2. Architecture

```
user text
  │
  ▼
[1 Neutralizer] → neutral_question + extracted claims (tagged user_asserted) + removed_cues
  │
  ▼
[2 Pre-flight Bias Audit] → pass / re-neutralize (max N) / ask user to clarify
  │            (checks: leading words, presupposition, loaded terms, identity cues, meaning drift)
  ▼
[3 Context Builder] ← [Fact Ledger]   only `established` facts enter as facts;
  │                                    `user_asserted`/`contested` enter labeled as such
  ▼
[4 Claude call] system prompt: neutral, calibrated, no flattery, state uncertainty, steelman alternatives
  │
  ▼
[5 Post-processor] → v1: remove flattery/unsupported-agreement openers only (D5);
  │                   preserve conclusions, uncertainty, citations; keep original for audit;
  │                   extract new claims
  ▼
[6 Ledger update] evidence-gated (D3); user objection → recheck (D4), not an automatic flip or a refusal to update
  │
  ▼
answer to user (+ optional "what I changed in your question" diff)
```

### 3.1 Neutralizer (D2: annotate, don't strip)
- Rules **detect and annotate** suspect spans (pressure, flattery, authority-as-argument, leading tags); they never globally delete words.
- **Protected spans** (exact-checked, never altered): numbers/quantities, negation, modality/uncertainty ("I think I took 10 mg"), attribution, quoted text, code, constraints, preferences, requested language/dialect.
- Task-relevant personal context (e.g. "I am pregnant") is kept as attributed context, not removed. Only interpersonal pressure is separated from substance.
- Minimal structured rewrite (small model), schema: `{task_parts[], relevant_context[], attributed_assertions[], preferences_constraints[], ambiguities[], edits[{span, action, reason}]}`. Multi-part questions stay multi-part.
- When uncertain → identity rewrite (no change) + visible note. Never silently change the task.
- Entailment/round-trip checks are diagnostics only; the gate is independently annotated preservation fixtures + exact protected-span checks.
- Show-the-diff mode so users see and can veto every edit.

### 3.2 Pre-flight Bias Audit
Independent checker (different prompt, ideally different model) scoring: leading language, presupposition, loaded terms, one-sided framing, hidden stakes ("my boss thinks..."). Output is a rubric score + reasons. Fail → re-run neutralizer, then ask user a clarifying question instead of guessing.

### 3.3 Fact Ledger (neutral context store)
- Storage (D3): SQLite (transactional) + versioned JSONL export. Namespaced by project/session; supports expiry, deletion, user inspection.
- Claim fields kept separate: `status`, `evidence_quality`, `confidence`. Evidence items record provenance, excerpt, scope, date, and supports/contradicts.
- Append-only change events with reasons; updates never erase prior evidence.
- **No promotion** from repetition, user insistence, or model consensus (agreeing samples are not independent evidence).
- A document can establish *what someone said* without establishing that it is *true*; the ledger records which.
- User self-reports and preferences stay as **attributed context** usable for the task; they don't need external proof.
- Task state and preferences live beside the evidence ledger, so context compression doesn't lose the user's actual task.
- Context handed to the model is a compact digest, not raw history. Contamination is tested through retrieved text and summaries too.

### 3.4 Claude call
Fixed system prompt: answer the neutral question; treat attributed assertions as unverified claims; state confidence from evidence; no unsupported agreement; warmth and empathy allowed.
**Objection rule (D4, replaces "never change without new evidence"):** a user objection triggers a recheck. It is neither proof nor something to ignore. Change position when the recheck finds new evidence, a calculation/reasoning error, or an ambiguous premise; otherwise keep it and explain why.

### 3.5 Post-processor (output neutrality, D5)
- Edits must preserve conclusions, uncertainty, citations, caveats, and instructions. No evidence-free confidence changes.
- Neutral ≠ equal weight: no generic "both sides" or "model-prior" disclaimers replacing a well-supported answer. Present several positions only when evidence is genuinely mixed.
- Scope v1: remove flattery and unsupported-agreement openers only. Original answer always kept for audit.
- A no-postprocessing arm is evaluated before any generative postprocessor ships.
- Extract claims → ledger (subject to §3.3 rules).

## 4. Delivery targets

**Mode boundaries (D6):** *strict* = the API/CLI path, where we build the full answering request and prove isolation with captured/mock provider payloads. *Advisory* = Claude Code hook and Claude app, where the original prompt still reaches the model. Docs and README label these modes honestly. Order: CLI/API first (§4.3), integrations after the core passes G4.

### 4.1 Claude Code (advisory mode)
Plugin containing:
- `UserPromptSubmit` hook: adds the neutral restatement + ledger digest + answering rules as context. It cannot replace the original prompt; `suppressOriginalPrompt` affects only the block message (per Codex A5, docs-verified, runtime test pending).
- `/neutral <question>` command: advisory. It asks Claude to answer the neutralized form, but the original text is still in the session context. It is NOT strict mode (D6) unless captured payloads prove isolation.
- `neutralizer` and `bias-auditor` subagents (isolated context, so the user's tone never reaches them in the answering path where avoidable).
- Skill `unbias` (SKILL.md) for auto-trigger on opinion/feedback/"are you sure?" situations.
- `CLAUDE.md` snippet for non-plugin users.
- `/ledger` command to view/edit facts; `/unbias off|on|strict` modes.
- One-line install: `/plugin marketplace add <org>/unbias-ai` then `/plugin install unbias@unbias-ai` [verify syntax].

### 4.2 Claude app (claude.ai / desktop)
- Project custom instructions (copy-paste, lite mode: no ledger enforcement).
- Skill zip upload (if available on the user's plan) [verify].
- MCP connector exposing `neutralize`, `audit`, `ledger_*` tools for full mode (remote or local MCP).
- Browser extension is out of scope for v1.

### 4.3 Library/CLI
`pip install unbias-ai`; `unbias ask "..."`; Python API `Unbiased(client).ask(...)`; works as a wrapper around the Anthropic SDK.

## 5. Evaluation plan (the credibility engine)

Principle: evals are a deliverable, run in CI, with numbers in the README.

### 5.1 Public benchmarks to leverage [all verify: current repos, licenses, splits]
| Eval | Measures | Use |
|---|---|---|
| Anthropic/Sharma et al. "Towards Understanding Sycophancy" (sycophancy-eval: feedback, answer, are-you-sure, mimicry) | feedback sycophancy, caving to pushback, mimicry | primary |
| Perez et al. model-written evals (sycophancy sets: NLP/philosophy/politics) | opinion matching user identity | primary |
| SycEval / FlipFlop-style multi-turn challenge | flip rate under rebuttal | primary |
| ELEPHANT (social sycophancy) | face-saving/validation behaviors | secondary |
| Syco-bench or similar | multiple sycophancy axes | secondary |
| TruthfulQA, SimpleQA/MMLU subset | no accuracy regression, no over-hedging | regression guard |
| BBQ / bias suites | no new demographic bias from rewriting | guard |
| Anthropic Petri / Bloom auditing tools | automated behavior probing | exploratory |

### 5.2 Custom evals we must build (no public set covers these)
1. **Tone-invariance**: each seed question rendered in N tones (neutral, confident-wrong, angry, flattering, authority-claim, emotional); metric = claim-level agreement of answers vs neutral baseline. Compare raw Claude vs unbias.
2. **Context-contamination**: multi-turn where turn 1 injects a user opinion/false premise; measure whether it appears later as a fact.
3. **Ledger integrity**: pressure-only pushback ("you're wrong, I'm an expert") must not change `established` entries; new evidence, a demonstrated reasoning/calculation error, or an exposed ambiguous premise must (D4).
4. **Meaning-preservation** of the neutralizer: human-labeled set + NLI check; also measure information loss.
5. **Output neutrality**: flattery/validation phrase rate, hedging calibration (ECE-style).
6. **Cost/latency**: added tokens, p50/p95 latency, $ per 100 questions.
7. **Over-correction check**: does unbias become contrarian or robotic? Measure agreement when the user is actually right.

### 5.3 Methodology
Authoritative spec: `evals/PROTOCOL.md` (gates G0–G5, metrics, release criteria). The bullets below are a summary.
- Pre-register metrics and thresholds in `evals/PROTOCOL.md` before first run.
- Arms: raw Claude, system-prompt-only ("don't be sycophantic"), unbias-lite, unbias-full. The prompt-only arm is the honest baseline.
- Judge controls: different judge model family where possible, randomized order, human-labeled calibration subset, report judge agreement.
- Multiple seeds/temps, confidence intervals, publish raw outputs + configs. Pin model IDs; rerun on new models.
- Report negative results.

## 6. What makes a repo go viral (checklist)

**Core**: sharp one-line pitch; before/after demo (the same pushy question answered raw vs unbias, side by side GIF/asciinema); 60-second quickstart; real benchmark chart in README top fold; one-line install.
**Repo hygiene**: LICENSE (MIT or Apache-2.0), README with badges (CI, PyPI, license, eval score), CONTRIBUTING, CODE_OF_CONDUCT, SECURITY.md, CHANGELOG, CITATION.cff, issue/PR templates, labeled `good first issue`s, Discussions on, ROADMAP.md.
**Engineering**: CI (lint, types, tests, eval smoke), pre-commit, semantic versioning + tagged releases, PyPI publish via trusted publishing, pinned deps, Dependabot, minimal required config, works with no API key for the demo mode (recorded fixtures).
**Docs**: docs site (mkdocs-material), "How it works" diagram, "Limits and honest caveats", examples folder, FAQ, comparison vs "just prompt it".
**Trust**: privacy statement (what is stored where; ledger local-only by default), no telemetry by default, reproducible evals, clear non-goals.
**Distribution**: Show HN, X/LinkedIn thread with the GIF, r/ClaudeAI + r/LocalLLaMA + r/MachineLearning post, a short blog post with the eval findings, submit to awesome-claude-code lists and plugin marketplaces, outreach to sycophancy researchers for feedback, a public leaderboard page that invites other models/mitigations.
**Naming/brand**: short memorable name, clean logo, consistent social card (OG image).

## 7. Milestones

| M | Deliverable | Exit criterion |
|---|---|---|
| M0 | Spec: decisions D1–D7, `evals/PROTOCOL.md`, fixture schema | Codex G0 PASS |
| M1 | Repo skeleton, CI, eval harness + raw/prompt-only baselines | Codex G1 PASS |
| M2 | Neutralizer + audit, preservation fixtures (≥40 families) | Codex G2 PASS |
| M3 | Fact Ledger + context builder | Codex G3 PASS |
| M4 | Post-processor, full pipeline, ablations (raw / prompt-only / rewrite-only / full) | Codex G4 PASS + release criteria in PROTOCOL §6 |
| M5 | Claude Code plugin + Claude app setup + docs + demo GIF | Codex G5 PASS; clean-machine install under 2 min |
| M6 | Launch assets, v0.1.0 release, launch posts | published |

## 8. Risks
- Neutralization changes meaning or strips needed context → diff view, drift guard, user veto.
- Over-correction (contrarian, flat, evasive) → over-correction eval, arm comparison.
- Added latency/cost → small model for stages 1-2, caching, lite mode.
- Judge bias in evals → human-labeled subset, cross-family judges.
- Ledger poisoned by wrong "facts" → evidence-gated promotion, expiry, user-visible edits.
- Benchmark contamination/overfitting to public sets → held-out custom evals.
- Claims outrunning evidence → README states measured results only.

## 9. First actions
1. Codex answers Q1-Q5 in `COMMON_CONTEXT.md`.
2. CC verifies all `[verify]` items (repos, hook semantics, plugin install syntax).
3. Pick name + license, scaffold repo, wire CI.
4. Build the eval harness before the product.
