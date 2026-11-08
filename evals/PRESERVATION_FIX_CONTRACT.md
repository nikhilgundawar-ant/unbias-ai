# N-2 proposal for agreement — preservation safety

CX review proposal, 2026-11-07 UTC. This is design input for CC, not an approved schema change. RS-1 collection is independent and must not be rerun for these changes.

## Narrow repair to agree first

1. A substring-only removal request with multiple occurrences is ambiguous. Fall back to the unchanged message instead of applying the request to every occurrence. Do not select the first occurrence silently.
2. A later occurrence-specific format may add integer start/end offsets plus an exact source substring. Validate bounds, exact source equality, occurrence identity, overlap and ordering. Reject malformed/bool offsets. Agree the format and update extraction instructions before implementing it; old saved extractions must remain auditable under their original format.
3. Check the final extended cut range, including punctuation/space, against all declared protected ranges. Content retained as task, relevant context, attributed assertion or preference/constraint cannot also be cut. Any overlap is a fallback, not a choice of which model label to believe.
4. Protect quoted/code content without the current 400-character quote cap. Unclosed delimiters require conservative handling; a parser's uncertainty cannot authorize deleting the remainder. Avoid treating every apostrophe in a contraction as a quote boundary.
5. Preserve the original message and exact proposed/actual ranges in the audit. Fallback reasons, identity outcomes and successful authorized removal remain distinct.

## What these repairs do not establish

The classifier can omit relevant context or label it pressure. Exact ranges and an independent regex cannot prove that a phrase is irrelevant. The role/emotion/reporting/anaphora cases in the fixed CX set expose that residual risk. A second model's agreement also is not proof.

Until that risk is independently evaluated, automatic editing remains a prototype. An annotation/diff path can show proposed cuts for review; it must not claim the answering model received neutral input unless the approved edited message is actually used. The user must see whether edits were proposed, applied or rejected. Do not silently substitute a no-edit mode and call the mitigation successful.

## Required review evidence

- Run the frozen 24-family CX suite with original character-range checks. Keep the original expectations. An intentional safe fallback on the repeated-phrase oracle is a safety improvement but does not satisfy that oracle's desired selective removal; report both facts.
- Add independently authored CC families to reach the agreed 40-family development minimum before G2 review. Keep development coverage distinct from held-out/human validation and live semantic quality.
- Add schema/offset/overlap and quote-boundary failure controls after the format is agreed. No model calls are required for these verifier tests.
- Report unsafe edits, preservation, removal coverage, safe/unexpected fallbacks and unsupported language cases separately. Do not maximize precision by silently counting identity as successful mitigation.

G2 remains changes requested until the relevant evidence is reviewed. Passing a finite development suite cannot support a universal unbiased-language or lossless-rewriting guarantee.
