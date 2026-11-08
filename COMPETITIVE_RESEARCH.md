# Competitive research — unbias-ai

Observed 2026-11-07 UTC. Owner: CX. Research and recommendations, not measured superiority or an agreed scope expansion. Star counts below are retrieved GitHub snapshots; rounded values are GitHub UI displays. Counts change, and some pages are cached.

## Finding

The problem and several approaches already exist. High-star projects offer adjacent tooling, and a high-star skill collection contains a directly relevant anti-sycophancy skill. This search did **not verify a standalone, thousands-star project with our exact proposed end-to-end design**. That is a bounded search finding, not evidence that none exists. GitHub repository search through the web tool failed; topic pages, repository pages, primary skill sources, API metadata and papers were inspected instead.

The defensible opportunity is a useful, transparent wrapper whose additional benefit over inexpensive alternatives is demonstrated. Stars are an adoption outcome; neither technical quality nor a launch plan can guarantee the largest count.

## Verified comparison

| Project | Observed stars | What was verified | Implication for us |
|---|---:|---|---|
| [Caveman](https://github.com/JuliusBrussee/caveman) | **118,084**, [API](https://api.github.com/repos/JuliusBrussee/caveman) | Skill and proxy aimed at token reduction; its savings figure is the project's claim, not our measurement. | Study its understandable pitch and lightweight entry point. It addresses a different problem. |
| [Superpowers](https://github.com/obra/superpowers) | **313,751**, [API](https://api.github.com/repos/obra/superpowers) | Broad agent workflow framework. Its [review skill](https://github.com/obra/superpowers/blob/main/skills/receiving-code-review/SKILL.md) already asks for technical verification and reasoned pushback. | “Makes agents push back” is insufficient differentiation. Integrating with existing workflows is preferable to recreating the framework. |
| [Agentic Awesome Skills](https://github.com/sickn33/agentic-awesome-skills) | **~49.3k** | Catalog contains an [anti-sycophancy skill](https://github.com/sickn33/agentic-awesome-skills/blob/main/skills/anti-sycophancy/SKILL.md) directing independent claim assessment and evidence-based responses. It identifies an upstream community source. | Direct prompt-level alternative and possible future distribution channel. Catalog stars do **not** belong to this individual skill. |
| [Promptfoo](https://github.com/promptfoo/promptfoo) | **~26.9k** | General prompt/agent evaluation and red-team tooling with CLI/CI integration. | Adjacent evaluation infrastructure. We have not verified a specific sycophancy plugin; do not claim one exists or is absent. |
| [Guardrails](https://github.com/guardrails-ai/guardrails) | **7,586**, [API](https://api.github.com/repos/guardrails-ai/guardrails) | Input/output validation framework with composable validators. | Input/output interception itself is established engineering. Our particular behavior and evidence must distinguish us. |
| [Graphiti](https://github.com/getzep/graphiti) | **~32.6k** (18:54 UTC follow-up) | Temporal context graph framework; [README](https://github.com/getzep/graphiti/blob/main/README.md) describes provenance, validity windows and historical queries. Adjacent memory infrastructure, not a verified anti-sycophancy wrapper. | Provenance and evolving memory are established approaches. Test our specific evidence-promotion rules and context rendering; do not market the existence of a fact ledger as novel or import a graph framework without a demonstrated need. |
| [Anti-sycophancy prompt](https://github.com/talhapythoneer/anti-sycophancy-prompt) | **22** | Direct copyable system-prompt alternative. | Include a credible low-overhead prompt baseline; do not equate a bibliography with validated effectiveness. |
| [Epistemic calibration protocol](https://github.com/RaulLzn/epistemic-calibration-protocol) | **1** | Anti-sycophancy protocol with an adversarial evaluation harness. | A prompt plus tests is already represented. |
| [Anti-sycophancy benchmark suite](https://github.com/antisycophancy/anti-sycophancy-benchmark-suite) | **1** | Adaptive multi-turn evaluation, artifact contracts and a dashboard. README explicitly discloses judge-calibration and scope limitations. | Reproducibility is valuable but not unique. Compare or reuse relevant evaluation approaches after checking dataset terms and compatibility. |
| [0xcjl/anti-sycophancy](https://github.com/0xcjl/anti-sycophancy) | **10** | Reframing-oriented hook, skill and persistent instruction layers, explicitly citing the same reframing paper. | A layered Claude Code anti-sycophancy package already exists. Compare actual request visibility and behavior; do not assume a hook replaces the original prompt. |
| [no-sycophancy](https://github.com/waitdeadai/no-sycophancy) | **0** | Claude Code Stop-hook patterns block configured praise openers, with an encouragement-request exception. | Removing praise openers is already a lightweight option. We must measure substantive judgment, not merely fewer compliments. |
| [I Can't](https://github.com/achen919/Icant) | **0** | Evidence-gated Codex skill/plugin with pressure and valid-reversal probes, positive controls and published smoke outputs. Its README disclaims general/statistical improvement from its small test. | Evidence gates, correction controls and honest smoke-test disclosure are already represented. Our implementation must establish its particular added value. |
| [FutureSpeak anti-sycophancy](https://github.com/FutureSpeakAI/anti-sycophancy) | **4** | Runtime calibration/circuit-breaker package, archived October 2026; README directs users to Agent-Friday. | Runtime anti-sycophancy packaging is also prior art. Style/sentiment signals should not substitute for factual-stance evaluation. |

These are different categories, not an efficacy ranking. None was installed or benchmarked for this research. No absence-of-feature claim follows from a README inspection. The four closer runtime/skill alternatives above were added in a second search pass; their small counts do not establish market size or technical quality.

## Material research prior art

[Dubois et al., *Ask don't tell*, v4, July 2026](https://arxiv.org/html/2602.23971v4) studies input reframing and reports benefits from converting non-questions to questions. Methods §4.1.4 describes an answering-model instruction, including an already-question control. Its evidence does not establish our proposed ledger, separate rewriting model, multilingual preservation or production performance.

**Consequence:** credit prior art. Add a separately labeled, paper-inspired question-reframing comparator after agreeing its exact implementation. Preserve the registered primary comparison; do not call an adaptation an exact replication. Any claimed benefit from our extra stages must justify their cost against this simpler approach as well as the strong prompt-only baseline.

## Proposed advantage to prove

Proposed positioning: **“Your tone shouldn't change the facts.”** Product description: a local wrapper that helps test and reduce framing-driven changes while preserving the user's actual task.

1. **Visible meaning preservation:** show the original request, proposed rewrite and reasons. Preserve quantities, negation, uncertainty, quotes/code, relevant context and requested language. Revert uncertain edits. Demonstrate this on independently labeled cases; a pleasant rewrite is not proof.
2. **Evidence across turns:** distinguish user assertions, sources, model answers and established support. Accept valid corrections without treating pressure or repeated agreement as evidence. Make the ledger inspectable, removable and exportable. This is a differentiation hypothesis, not verified exclusivity.
3. **A reproducible pressure test:** one command compares matched variants, reports correctness, correction uptake, flips, hedges, incomplete answers, refusals and missing outcomes alongside latency/cost. Include passing and failing cases; export artifacts other tools can inspect.
4. **A small usable entry point:** ship one working Claude workflow first, with an offline recorded demo and honest advisory/strict labels. Keep a no-extra-model-call baseline available. Add stages only when ablations show benefit. Claude-only implementation is the current constraint; additional providers are future scope, not a prerequisite.

Our current status: evaluation scaffolding and a provisional CLI baseline exist. Mitigation superiority, live grader calibration and strict request isolation have **not** been demonstrated. If simple prompting performs equally well, ship the simpler useful option rather than assert an advantage.

## Adoption plan to test

- First earn a narrow claim: better decisions under irrelevant pressure without losing meaning or valid-correction uptake. Publish the measured scope and failures, not “bias eliminated” or “best AI wrapper.”
- Make the first screen concrete: an explainable example, a short install, a recorded offline demo, a reversible switch and a link to the complete run. Label curated examples and make selection reproducible.
- Test onboarding with an initial cohort of ten independent users. Proposed usability target: eight complete the documented first check without assistance. This is a target, not a forecast or study result.
- Track useful outcomes before stars: successful installations, repeated voluntary use, reported failures resolved, external fixture contributions, and reproducible community runs. Use opt-in reports rather than introduce default telemetry.
- Prepare integration examples for established skill/evaluation ecosystems; propose contributions through their normal processes only when we have a working, measured artifact. No external outreach, posting or publication has been authorized or performed here.
- Prepare a short reproducible demo and release notes once claims are supported. A comparison page should list conditions and tradeoffs, not declare victory over unrelated frameworks. Refresh popularity snapshots before launch.

Decision requested from CC: accept/challenge the narrow positioning and secondary reframing comparator. Existing implementation continues; do not add a feature merely to match a larger repository's checklist.

## Coordination update — 14:19 UTC

CC and CX accepted the narrow positioning, crediting prior art and adding a separately labeled paper-inspired comparator without changing the primary criterion. Both also agreed to ship the pressure-test entry point first, beginning with offline replay and explicit live resource limits. This is an implementation priority, not demonstrated market demand. The neutralizer and evidence ledger remain on the wrapper roadmap. Core development and independent evaluation continue alongside this research; no launch or external outreach has occurred.

## Validation reuse follow-up — 15:12 UTC

[Pander Score](https://github.com/sophronresearch/pander-score) releases framing prompts, saved outputs and human-judgment validation tables; its [data contract](https://github.com/sophronresearch/pander-score/blob/main/docs/data.md) describes evidence/credence filtering. [ELEPHANT](https://github.com/myracheng/elephant) includes social-sycophancy datasets and human-response baselines. These are candidates for external validation, not substitutes for our factual-claim calibration or proof of its accuracy. Check label semantics and dataset terms before reuse. No full benchmark was run; Pander's full live workflow also requires judges outside the current Claude-only scope. Existing data inspection may be more useful than adding another proprietary judging mechanism.

## Further primary-source review — 18:53 UTC

[Reality Filter Protocol](https://github.com/RuizHernandez/reality-filter-protocol) showed **4 stars**. It combines portable anti-sycophancy instructions, evidence labels and multi-agent authority boundaries, and explicitly distinguishes prompt guidance from enforcement. Its README disclaims a controlled behavioral A/B evaluation. Our reviewer/orchestrator role and evidence-first instructions are therefore not novel product claims; independently checked runtime behavior remains the opportunity to prove.

The [Inspect sycophancy task](https://github.com/UKGovernmentBEIS/inspect_evals/blob/main/src/inspect_evals/sycophancy/README.md) implements the challenge-after-answer setting. It documents duplicate removal and past denominator/scoring fixes. Reusing a framework does not remove the need to verify scoring and sample accounting. No installation or benchmark run was performed.

[Anthropic's model-written sycophancy data](https://github.com/anthropics/evals/blob/main/sycophancy/README.md) measures agreement with biography views through answer-choice probabilities. Its behavior labels are not factual-correctness labels. Our current CLI does not expose those probabilities; sampled-choice adaptation would require a separate protocol and could not be called an exact reproduction. Neither dataset nor the findings alter the frozen RS-1 batch.
