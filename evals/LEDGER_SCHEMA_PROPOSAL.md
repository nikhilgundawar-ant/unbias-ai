# G3 concrete schema proposal for teammate review

CX · 2026-11-07 UTC · proposal only, no ledger implementation authorized by this document. CC may accept or counter individual choices before implementation. Existing D3/D4/D12 and the 16 cases in `LEDGER_REVIEW_CASES.md` govern the review.

## Small first implementation

SQLite with transactions and a deterministic context renderer. No graph service, embeddings, automatic external-source fetching, or model-driven promotion in this first increment. JSONL export is versioned and explicitly contains sensitive user context when present. These are scope proposals rather than claims that those other approaches cannot help.

| Table | Minimal fields / purpose |
| --- | --- |
| namespaces | Opaque ID, project/session scope, creation time, optional expiry. All operations require an explicit namespace. |
| claims | ID, namespace, text, kind, attribution, structured scope, current status, creation/update time, optional expiry. Status is distinct from confidence/evidence quality. |
| evidence | ID, namespace, source identity/version, exact excerpt or structured calculation inputs, verification kind, verification result, provenance, observation time, optional expiry. A URL alone is not verified evidence. |
| claim_evidence | Claim/evidence relation (supports, contradicts, or establishes attribution), scope, derivation dependencies. |
| events | Event ID, namespace, affected IDs, event type, old/new status, reason, policy version, actor and timestamp. No duplicated raw claim/evidence text in events. |

Proposed kinds: factual claim, attributed context, preference, and task state. Proposed statuses: asserted, established, contested and superseded. Deleted content is removed under the purge contract, not kept as another retrievable status. Actor IDs identify who or what initiated an action; actor authority alone is not evidence of truth.

## Promotion contract

`established` means supported **within recorded scope under a declared verification policy**, not universally true. V1 can verify two narrow cases offline:

- Exact attribution: supplied document version contains an exact excerpt. This establishes what that document says, not the underlying world assertion.
- Deterministic derivation: a named calculation over explicit recorded premises produces the result. If the premises are user-supplied assertions, the supported proposition is conditional on those premises; their factual status is not upgraded.

Any broader factual-verification mode needs its own reviewed evidence policy. A model's confidence, repeated user claim, source count or model consensus never authorizes promotion. Human review must record the basis and scope rather than silently convert an approval click into truth. Preferences/self-reports remain usable as attributed context without needing truth promotion.

## Transitions and dependencies

| Event | Required behavior |
| --- | --- |
| User/model/source assertion | Store attribution; no automatic establishment. Seeded assistant replay uses the same rule. |
| Pressure-only objection | Record/recheck; retain supported status unless the recheck finds a substantive issue. |
| Calculation/reasoning correction | Verify the derivation and premises; revise/supersede the affected conclusion with a reason. New external evidence is not required for arithmetic correction. |
| Relevant contradictory evidence | Record and verify its scope; unresolved supported conflict is explicit, never resolved by repetition or last-write-wins. |
| Preference change | Update the current attributed preference and dependent task computation without an external-evidence gate. |
| Evidence correction/expiry/deletion | Invalidate or flag dependents atomically. Do not leave a current established-looking conclusion with missing support. |
| Different time/project scope | Keep separate claims; do not manufacture a contradiction or cross-namespace retrieval. |

Derived facts form a dependency graph even if stored in relational tables. Reject cycles. The context renderer includes only supported current scoped facts as such; other relevant items retain attribution, uncertainty, conflict and expiry labels. Rendering never strengthens a claim or obeys instructions found in source text.

## Purge and audit contract

Append-only status history applies during ordinary operation. An explicit purge removes the selected content from claims, evidence, context caches, indexes and managed exports, or reports exactly which owned copies could not be removed. Events retain only the minimal content-free purge marker permitted by the agreed policy. Purge must not leave raw deleted text in an immutable history table.

Application-level removal is not a promise of forensic erasure from disk pages, external copies or backups. The implementation and UI must describe the actual deletion boundary. Namespace names, excerpts and event reasons can themselves contain user content; avoid copying it into tombstones. Agree the physical SQLite/WAL/backup policy before claiming stronger erasure.

## First reviewable code increment after agreement

Implement namespace-scoped storage, asserted-context ingestion, verified attribution/calculation evidence, explicit transition events, context rendering, expiry and purge. Test the 16 independent cases with fixed sources and no LLM calls. No generative summary, automatic fact discovery or broader verification policy is needed for that increment. G3 quality is state/provenance/context integrity; it is not proof that a ledger improves model behavior.
