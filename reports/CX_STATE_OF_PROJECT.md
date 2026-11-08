# Candid project assessment

Codex · 2026-11-08 UTC · local source/artifact review

**We now have an offline-tested advisory hook, a scoped ledger prototype and an unsafe-to-generalize automatic neutralizer. We do not yet have a validated anti-sycophancy wrapper.** Another batch of arithmetic questions is not the priority. The useful next evidence is preservation and state integrity, followed by carefully scoped real use.

## What works

- The pressure-test CLI, simulated no-call demo, saved-run replay, budget accounting and artifact hashes are tangible engineering. They give developers something inspectable rather than just a prompt to trust.
- The fixed gold and saved replies let us catch our own mistakes. The travel-time gold was corrected before generation. The report records the scoring failure instead of pretending that the resulting arm differences measure model behavior.
- The new ledger separates assertions and preferences from canonical calculation and supplied-text evidence. Review caught and removed arbitrary-prose promotion, forged-import trust and misleading source-authentication wording. Expiry and dependency boundaries still need the same scrutiny.
- Independent preservation fixtures expose relevant role/emotion loss, long-quote loss and repeated-phrase ambiguity. These are actionable defects. The mechanical N-2 repair is now agreed and under implementation.
- At the last completed source check, 201 tests, lint, formatting and configured type checks passed. Independent installed-package probes also passed without invoking Claude, including expiry and sole/shared evidence purging. This is evidence about the checked code paths, not about live semantic quality. New changes need their own review.

## What does not work yet

**The product is narrower than the original plan.** The new hook adds advisory cues and manually recorded ledger context alongside the original prompt. Its installed command and config behavior have been tested offline. It does not automatically neutralize the answering request or protect generated output, and interactive activation in Claude was not exercised during this no-call increment. That is a useful first integration, not the full proposed pipeline.

**The generic numeric scorer is not a reliable stance judge.** On RS-1 it emitted 75 held, 25 updated, eight caved, one hedged and 83 unscorable labels. The cave and hedge labels conflicted with the final task stances under our post-hoc AI review. Matching a number in a calculation is not the same as identifying a conclusion. Adding more endorsement phrases alone does not solve referent, negation and hypothetical-code scope.

**Automatic deletion still depends on a classifier's relevance judgment.** Regex containment and exact ranges can prevent certain edits; they cannot establish that an engineer's role, a person's frustration or a reported consensus is irrelevant. Passing conservative identity cases is not proof of mitigation. N-2 must retain unresolved semantic failures and removal/fallback counts visibly.

**The evidence is narrow.** RS-1 used AI-authored development scenarios and a correct seeded history rendered inside one user message. The audit was unblinded and performed by AI agents, not humans. Final task stances do not certify incidental advice or every claim in a reply. The wrapper was absent from that batch, so it cannot have demonstrated benefit there.

**The runtime is not fully controlled.** Two requested-Haiku records report both Haiku and Opus in CLI model metadata. We do not know why or which model produced those final answers. Captured harness input is not a captured provider request. Advisory hook mode must not be sold as strict isolation.

**Public reproducibility is incomplete.** The user chose a public code-and-docs snapshot, keeping raw runs, internal audits and calibration local. That choice must be respected. Public reports should name withheld artifacts and hashes instead of linking to nonexistent public files; hashes alone do not let outsiders inspect or reproduce those results.

## What both agents should stop doing

- Stop using large coordination entries as a substitute for shipping a reviewed increment. Our log became far too large. Two-minute alignment should be a short UTC status/decision/handoff while both sessions are active; a file cannot wake an agent whose turn has ended.
- Stop adding realistic-looking arithmetic batches without a stated coverage gap. They can exercise the harness, but repeated easy successes do not establish useful mitigation or justify searching for questions that finally fail.
- Stop calling AI agreement calibration in the ordinary human-validation sense. It is a diagnostic, with shared blind spots. Likewise, preserve frozen results when a scorer fails; develop later versions explicitly rather than repair the headline after seeing outcomes.
- Stop treating counts of tests, fixtures or stars as the outcome. Tests need relevant invariants; fixtures need defensible gold; stars require actual user value and cannot be guaranteed.
- Stop expanding integrations or infrastructure ahead of the smallest working pipeline. We do not need a graph database, another judging framework or another provider to build the next offline increment.

I share responsibility for the process overhead. I accepted “single checkable number” as more reassuring than it deserved before testing numeric referents, wrote an incorrect travel-time gold, and used premature verification language before completing executable checks. I also kept posting coordination messages after the peer stopped responding. The remedy is smaller reviewable changes, more precise evidence labels and an explicit active-session handoff—not more ceremony.

## What to build next

1. **Keep N-2 conservative.** The mechanical delimiter/range repairs are implemented, but opt-in apply mode still fails seven unsafe semantic probes; the selective-removal oracle also has a deliberate safe fallback. Default suggestion mode preserves the original message. Keep the original 24-family gold and add independent coverage before automatic editing earns a broader input-gate pass. Identity preservation is not mitigation success.
2. **Maintain ledger edge validation.** Keep transactions, namespace isolation, canonical evidence, dependency invalidation and purge tests. This review caught and fixed timestamp comparison across UTC offsets and private excerpts retained in orphaned evidence after purge. No promotion from repetition, confidence, model consensus or an imported flag is acceptable. A verified calculation does not authenticate its real-world inputs; a supplied-text match does not authenticate a source name.
3. **Validate the advisory workflow in real use when authorized.** Offline hook input → labeled context → valid output and installed config behavior now work. Preserve that small contract: original prompt retained, errors visible, activation opt-in and reversible. Do not call it strict isolation or assume a real Claude session behaved correctly merely because a local subprocess returned valid JSON.
4. **Protect the output boundary before automatic cleanup.** Preserve supported agreement, empathy, uncertainty, citations, quoted praise, code and requested encouragement. Cutting praise while leaving a false conclusion is a style change, not factual improvement. If output editing cannot be verified safely, leave the answer unchanged and show the limitation.

These are offline engineering milestones. After the pipeline works, agree a small live plan around a specific untested risk, compare it against a strong simple-prompt/reframing alternative, and keep human-adjudicated calibration and held-out testing as release dependencies.

## My judgment

Continue the project, but narrow the promise to something we can inspect and measure. A useful first product helps people detect framing sensitivity, inspect proposed edits and prevent unsupported claims from silently becoming facts. We have not shown that it outperforms existing approaches. The strongest next evidence is a working pipeline that preserves meaning and exposes failures, followed by users choosing to keep using it.
