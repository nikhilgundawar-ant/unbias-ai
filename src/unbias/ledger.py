"""Evidence ledger G3 v1 (CX schema proposal, accepted 2026-11-08). No model calls.

A claim is never true because someone said it, repeated it, or a model agreed. Claims carry
attribution, scope and a status; only two narrow, offline-verifiable paths can establish one:

- exact attribution: a document version contains an excerpt -> establishes "<source> says X",
  never the world assertion X itself (L04);
- deterministic derivation: a named calculation over recorded premises reproduces the result.
  If any premise is not itself established, the derived claim is established *conditionally*
  and rendered that way.

Pressure, titles, repetition, model consensus and source text cannot change status (L01, L02,
L06, L13). Preferences are attributed context and update without an evidence gate (L10).
Purge removes content and leaves only a content-free tombstone event (L14). Deletion boundary:
rows are removed from this SQLite database (with secure_delete on); copies in backups, WAL
checkpoints not yet run, exports or other systems are outside this guarantee.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from fractions import Fraction
from typing import Any

KINDS = ("factual", "attribution", "preference", "task_state")
STATUSES = ("asserted", "established", "contested", "superseded")
ATTRIBUTIONS = ("user", "assistant", "model", "source", "derived")
EXPORT_VERSION = "ledger-export.v2"  # v2 adds namespace metadata (CX R2)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS namespaces (
  id TEXT PRIMARY KEY, created_at TEXT NOT NULL, expires_at TEXT);
CREATE TABLE IF NOT EXISTS claims (
  id TEXT PRIMARY KEY, ns TEXT NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
  text TEXT NOT NULL, kind TEXT NOT NULL, attribution TEXT NOT NULL, scope TEXT NOT NULL,
  status TEXT NOT NULL, conditional INTEGER NOT NULL DEFAULT 0, pref_key TEXT, label TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, expires_at TEXT);
CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY, ns TEXT NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
  source TEXT NOT NULL, source_version TEXT NOT NULL, vkind TEXT NOT NULL,
  content TEXT NOT NULL, verified INTEGER NOT NULL, scope TEXT NOT NULL,
  observed_at TEXT NOT NULL, expires_at TEXT);
CREATE TABLE IF NOT EXISTS claim_evidence (
  claim TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  evidence TEXT NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
  relation TEXT NOT NULL, PRIMARY KEY (claim, evidence));
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ns TEXT NOT NULL, type TEXT NOT NULL,
  affected TEXT NOT NULL, old_status TEXT, new_status TEXT, reason TEXT,
  policy TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL);
"""
POLICY = "g3-v1"

# Deterministic derivations allowed in v1. Inputs are plain numbers.
# Exact rational arithmetic (CX 04:50): no float tolerance can certify a different number.
OPS: dict[str, Callable[[dict[str, Fraction]], Fraction]] = {
    "ratio_pct": lambda i: i["numerator"] / i["denominator"] * 100,
    "difference": lambda i: i["a"] - i["b"],
    "sum": lambda i: sum((v for _, v in sorted(i.items())), Fraction(0)),
    "product": lambda i: math.prod((v for _, v in sorted(i.items())), start=Fraction(1)),
    "ceil_div": lambda i: Fraction(math.ceil(i["numerator"] / i["denominator"])),
}


class LedgerError(ValueError):
    """A requested transition is not allowed by the v1 policy."""


@dataclass(frozen=True)
class Claim:
    id: str
    ns: str
    text: str
    kind: str
    attribution: str
    scope: dict[str, str]
    status: str
    conditional: bool
    expires_at: str | None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _ts(value: str | None) -> str | None:
    """Canonical UTC timestamp so stored strings compare correctly (CX 04:58). Offsets are
    converted to UTC; naive or invalid timestamps are rejected, never silently 'fresh'."""
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError) as e:
        raise LedgerError(f"invalid timestamp {value!r}") from e
    if dt.tzinfo is None:
        raise LedgerError(f"timestamp {value!r} has no UTC offset")
    return dt.astimezone(UTC).isoformat(timespec="microseconds")


def _now_ts(clock: Callable[[], str]) -> Callable[[], str]:
    def wrapped() -> str:
        v = _ts(clock())
        assert v is not None
        return v

    return wrapped


def _id() -> str:
    return uuid.uuid4().hex[:16]


def _scope(scope: dict[str, str] | None) -> str:
    return json.dumps(scope or {}, sort_keys=True)


class Ledger:
    def __init__(
        self, path: str = ":memory:", clock: Callable[[], str] = _now, *, _conn: Any = None
    ) -> None:
        if _conn is not None:  # read-only handle: no PRAGMA writes, no schema init
            self.db, self.clock = _conn, _now_ts(clock)
            self.db.row_factory = sqlite3.Row
            return
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA secure_delete = ON")
        self.db.executescript(_SCHEMA)
        self.clock = _now_ts(clock)

    @classmethod
    def open_readonly(cls, path: str, clock: Callable[[], str] = _now) -> Ledger:
        """Open an EXISTING ledger with SQLite mode=ro (P-1/CX 04:44): never creates the file,
        never runs schema setup, cannot write. Raises sqlite3.OperationalError if missing."""
        from pathlib import Path

        uri = Path(path).resolve().as_uri() + "?mode=ro"
        return cls(clock=clock, _conn=sqlite3.connect(uri, uri=True))

    # ---------- plumbing ----------

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """All-or-nothing: a failure inside rolls back every write (L15)."""
        try:
            yield self.db
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def _event(
        self,
        ns: str,
        type_: str,
        affected: list[str],
        actor: str,
        reason: str = "",
        old: str | None = None,
        new: str | None = None,
    ) -> None:
        self.db.execute(
            "INSERT INTO events (ns,type,affected,old_status,new_status,reason,policy,actor,at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (ns, type_, json.dumps(affected), old, new, reason, POLICY, actor, self.clock()),
        )

    def _require_ns(self, ns: str) -> None:
        if not self.db.execute("SELECT 1 FROM namespaces WHERE id=?", (ns,)).fetchone():
            raise LedgerError(f"unknown namespace {ns!r}")

    def claim(self, claim_id: str) -> Claim:
        r = self.db.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        if r is None:
            raise LedgerError(f"unknown claim {claim_id!r}")
        return Claim(
            r["id"],
            r["ns"],
            r["text"],
            r["kind"],
            r["attribution"],
            json.loads(r["scope"]),
            r["status"],
            bool(r["conditional"]),
            r["expires_at"],
        )

    def events(self, ns: str) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM events WHERE ns=? ORDER BY id", (ns,)).fetchall()
        return [dict(r) for r in rows]

    # ---------- writes ----------

    def namespace(self, name: str | None = None, expires_at: str | None = None) -> str:
        ns = name or _id()
        with self._tx():
            self.db.execute(
                "INSERT INTO namespaces VALUES (?,?,?)", (ns, self.clock(), _ts(expires_at))
            )
        return ns

    def assert_claim(
        self,
        ns: str,
        text: str,
        *,
        kind: str = "factual",
        attribution: str = "user",
        scope: dict[str, str] | None = None,
        actor: str = "user",
        expires_at: str | None = None,
    ) -> str:
        """Record what someone said. Always `asserted`; repeats never strengthen it (L01-L03)."""
        if kind not in KINDS or attribution not in ATTRIBUTIONS:
            raise LedgerError("bad kind/attribution")
        self._require_ns(ns)
        existing = self.db.execute(
            "SELECT id FROM claims WHERE ns=? AND text=? AND kind=? AND attribution=? AND scope=?"
            " AND status != 'superseded'",
            (ns, text, kind, attribution, _scope(scope)),
        ).fetchone()
        with self._tx():
            if existing:
                self._event(ns, "repeated", [existing["id"]], actor, "same assertion repeated")
                return str(existing["id"])
            cid, now = _id(), self.clock()
            self.db.execute(
                "INSERT INTO claims (id,ns,text,kind,attribution,scope,status,created_at,"
                "updated_at,expires_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    cid,
                    ns,
                    text,
                    kind,
                    attribution,
                    _scope(scope),
                    "asserted",
                    now,
                    now,
                    _ts(expires_at),
                ),
            )
            self._event(ns, "asserted", [cid], actor, new="asserted")
        return cid

    def add_excerpt_evidence(
        self,
        ns: str,
        *,
        source: str,
        version: str,
        document: str,
        excerpt: str,
        scope: dict[str, str] | None = None,
        expires_at: str | None = None,
    ) -> str:
        """Verified only if the excerpt is an exact substring of that document version.
        The document text is stored as data; nothing in it is ever executed (L13)."""
        return self._evidence(
            ns,
            source,
            version,
            "excerpt",
            {"excerpt": excerpt},
            excerpt in document and bool(excerpt.strip()),
            scope,
            expires_at,
        )

    def add_calculation_evidence(
        self,
        ns: str,
        *,
        op: str,
        inputs: dict[str, float],
        result: float,
        premises: list[str] | None = None,
        source: str = "calculation",
        version: str = "1",
        scope: dict[str, str] | None = None,
        expires_at: str | None = None,
    ) -> str:
        """Verified only if recomputing `op` over `inputs` reproduces `result`."""
        content = {"op": op, "inputs": inputs, "result": result, "premises": premises or []}
        ok, _ = _recompute(content)
        for p in premises or []:
            self._premise(p, ns)  # must exist, same namespace (CX 04:42)
        return self._evidence(ns, source, version, "calculation", content, ok, scope, expires_at)

    def _evidence(
        self,
        ns: str,
        source: str,
        version: str,
        vkind: str,
        content: dict[str, Any],
        verified: bool,
        scope: dict[str, str] | None,
        expires_at: str | None,
    ) -> str:
        self._require_ns(ns)
        eid = _id()
        with self._tx():
            self.db.execute(
                "INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    eid,
                    ns,
                    source,
                    version,
                    vkind,
                    json.dumps(content),
                    int(verified),
                    _scope(scope),
                    self.clock(),
                    _ts(expires_at),
                ),
            )
            self._event(
                ns, "evidence_added", [eid], "system", "verified" if verified else "NOT verified"
            )
        return eid

    # ---------- promotion: only canonical claims created FROM verified evidence ----------
    # CX 04:42: free-text claims are never blessed because they contain a token or substring.

    def _ev(self, evidence_id: str) -> sqlite3.Row:
        e = self.db.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()
        if e is None:
            raise LedgerError("unknown evidence")
        row: sqlite3.Row = e
        return row

    def _canonical(self, e: sqlite3.Row) -> tuple[str, str, str, bool]:
        """(text, kind, attribution, conditional) for the one claim this evidence supports."""
        content = json.loads(e["content"])
        if e["vkind"] == "excerpt":
            if not e["verified"]:
                raise LedgerError("excerpt was not verified against its document version")
            # CX 04:49: we verify a match against SUPPLIED text, not who the source is.
            text = (
                f"Supplied document labeled {json.dumps(e['source'])}, version "
                f"{json.dumps(e['source_version'])}, contains exact excerpt "
                f"{json.dumps(content['excerpt'], ensure_ascii=False)} "
                "(source identity not authenticated)"
            )
            return text, "attribution", "source", False
        ok, problem = _recompute(content)  # never trust a stored `verified` flag
        if not ok:
            raise LedgerError(f"calculation does not verify: {problem}")
        premises = [self._premise(p, e["ns"]) for p in content["premises"]]
        conditional = any(p.status != "established" or p.conditional for p in premises)
        return _calc_text(content), "factual", "derived", conditional

    def _premise(self, claim_id: str, ns: str) -> Claim:
        p = self.claim(claim_id)
        if p.ns != ns:
            raise LedgerError("premise is in a different namespace")
        return p

    def _create_established(
        self, e: sqlite3.Row, actor: str, reason: str, label: str | None
    ) -> str:
        text, kind, attribution, conditional = self._canonical(e)
        cid, now = _id(), self.clock()
        self.db.execute(
            "INSERT INTO claims (id,ns,text,kind,attribution,scope,status,conditional,label,"
            "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                cid,
                e["ns"],
                text,
                kind,
                attribution,
                e["scope"],
                "established",
                int(conditional),
                label,
                now,
                now,
            ),
        )
        self.db.execute("INSERT INTO claim_evidence VALUES (?,?,?)", (cid, e["id"], "supports"))
        self._event(e["ns"], "established", [cid, e["id"]], actor, reason, None, "established")
        return cid

    def attest_excerpt(self, evidence_id: str, *, actor: str, reason: str = "exact excerpt") -> str:
        """Establish that a supplied document contains an excerpt; never the excerpt's assertion
        (L04) and never that the named source really wrote it (CX 04:49)."""
        e = self._ev(evidence_id)
        if e["vkind"] != "excerpt":
            raise LedgerError("not excerpt evidence")
        with self._tx():
            return self._create_established(e, actor, reason, None)

    def derive(
        self, evidence_id: str, *, actor: str, reason: str = "recomputed", label: str | None = None
    ) -> str:
        """Establish 'op(k=v, ...) = result' after recomputing it. `label` is the user's own
        wording for it and is rendered as unverified text, never as part of the fact."""
        e = self._ev(evidence_id)
        if e["vkind"] != "calculation":
            raise LedgerError("not calculation evidence")
        with self._tx():
            return self._create_established(e, actor, reason, label)

    def object(self, claim_id: str, *, actor: str, reason: str) -> str:
        """Pressure-only objection (L06): recorded as a recheck request; status is unchanged.
        Real changes go through `supersede` with verified evidence or a corrected derivation."""
        c = self.claim(claim_id)
        with self._tx():
            self._event(c.ns, "objection_recorded", [claim_id], actor, reason, c.status, c.status)
        return c.status

    def supersede(
        self,
        old_id: str,
        evidence_id: str,
        *,
        actor: str,
        reason: str,
        label: str | None = None,
    ) -> str:
        """Replace a claim with the canonical claim its new evidence supports (L05, L07), in one
        transaction. Same namespace and scope only (L08). History is kept."""
        old, e = self.claim(old_id), self._ev(evidence_id)
        if e["ns"] != old.ns or json.loads(e["scope"]) != old.scope:
            raise LedgerError("supersession needs the same namespace and scope (L08)")
        with self._tx():
            new_id = self._create_established(e, actor, reason, label)
            self.db.execute(
                "UPDATE claims SET status='superseded', updated_at=? WHERE id=?",
                (self.clock(), old_id),
            )
            self._event(
                old.ns,
                "superseded",
                [old_id, new_id, evidence_id],
                actor,
                reason,
                old.status,
                "superseded",
            )
        return new_id

    def mark_conflict(self, claim_ids: list[str], *, actor: str, reason: str) -> None:
        """Same-scope disagreement stays visible; no vote or last-write-wins (L09)."""
        cs = [self.claim(i) for i in claim_ids]
        if len({(c.ns, json.dumps(c.scope, sort_keys=True)) for c in cs}) != 1:
            raise LedgerError("only same-namespace, same-scope claims can conflict (L08)")
        with self._tx():
            for c in cs:
                self.db.execute(
                    "UPDATE claims SET status='contested', updated_at=? WHERE id=?",
                    (self.clock(), c.id),
                )
            self._event(cs[0].ns, "conflict", claim_ids, actor, reason, None, "contested")

    def set_preference(self, ns: str, key: str, value: str, *, actor: str = "user") -> str:
        """Current attributed preference; a change needs no truth evidence (L10)."""
        self._require_ns(ns)
        with self._tx():
            old = self.db.execute(
                "SELECT id FROM claims WHERE ns=? AND pref_key=? AND status='asserted'", (ns, key)
            ).fetchone()
            cid, now = _id(), self.clock()
            self.db.execute(
                "INSERT INTO claims (id,ns,text,kind,attribution,scope,status,pref_key,"
                "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (cid, ns, value, "preference", "user", "{}", "asserted", key, now, now),
            )
            if old:
                self.db.execute(
                    "UPDATE claims SET status='superseded', updated_at=? WHERE id=?",
                    (now, old["id"]),
                )
            self._event(ns, "preference_set", [cid] + ([old["id"]] if old else []), actor)
        return cid

    def purge_claim(self, claim_id: str, *, actor: str) -> None:
        """Remove a claim's content and any events that could carry its text (L14). Supporting
        evidence (which can hold the same text, e.g. an excerpt) is removed too once no other
        claim references it (CX 04:59); evidence still shared by another claim is kept, because
        that claim depends on it. Dependents of a purged premise render as stale."""
        c = self.claim(claim_id)
        with self._tx():
            ev_ids = [
                r["evidence"]
                for r in self.db.execute(
                    "SELECT evidence FROM claim_evidence WHERE claim=?", (claim_id,)
                ).fetchall()
            ]
            self.db.execute("DELETE FROM claims WHERE id=?", (claim_id,))  # cascades links
            purged = [claim_id]
            for eid in ev_ids:
                still_used = self.db.execute(
                    "SELECT 1 FROM claim_evidence WHERE evidence=?", (eid,)
                ).fetchone()
                if not still_used:
                    self.db.execute("DELETE FROM evidence WHERE id=?", (eid,))
                    purged.append(eid)
            for pid in purged:
                self.db.execute(
                    "DELETE FROM events WHERE ns=? AND affected LIKE ?", (c.ns, f'%"{pid}"%')
                )
            self._event(c.ns, "purged", [], actor, "content removed")

    def purge_namespace(self, ns: str, *, actor: str) -> None:
        with self._tx():
            self.db.execute("DELETE FROM namespaces WHERE id=?", (ns,))
            self.db.execute("DELETE FROM events WHERE ns=?", (ns,))
            self.db.execute(
                "INSERT INTO events (ns,type,affected,reason,policy,actor,at)"
                " VALUES ('_purged','namespace_purged','[]','',?,?,?)",
                (POLICY, actor, self.clock()),
            )

    # ---------- reads ----------

    def _supports(
        self, claim_id: str, now: str, _seen: frozenset[str] = frozenset()
    ) -> tuple[bool, bool]:
        """(has support, support still valid). Support is invalid if evidence expired, or a
        premise expired, was superseded/contested/purged, or forms a cycle (L12, CX 04:42)."""
        if claim_id in _seen:
            return True, False  # cycle (only possible via corrupt/imported data)
        rows = self.db.execute(
            "SELECT e.expires_at, e.content, e.vkind FROM claim_evidence ce JOIN evidence e"
            " ON e.id = ce.evidence WHERE ce.claim=?",
            (claim_id,),
        ).fetchall()
        valid = all(r["expires_at"] is None or r["expires_at"] > now for r in rows)
        for r in rows:
            if r["vkind"] != "calculation":
                continue
            for p in json.loads(r["content"])["premises"]:
                prow = self.db.execute(
                    "SELECT status, expires_at FROM claims WHERE id=?", (p,)
                ).fetchone()
                if (
                    prow is None
                    or prow["status"] in ("superseded", "contested")
                    or (prow["expires_at"] is not None and prow["expires_at"] <= now)
                ):
                    valid = False
                    continue
                has, ok = self._supports(p, now, _seen | {claim_id})
                if has and not ok:
                    valid = False
        return bool(rows), valid

    def render(self, ns: str, now: str | None = None, max_chars: int | None = None) -> str:
        """Context for the answering model. Only current, valid, unconditional established
        claims are listed as verified; everything else keeps its label. Never strengthens.

        Every stored value is JSON-escaped so stored text cannot forge headings or statuses
        (CX 04:44). With `max_chars`, only WHOLE entries are included, followed by an omission
        note; an entry is never cut mid-text (that could sever negation or attribution)."""
        now = (_ts(now) if now else None) or self.clock()
        nsrow = self.db.execute("SELECT expires_at FROM namespaces WHERE id=?", (ns,)).fetchone()
        if nsrow is None:
            return ""
        if nsrow["expires_at"] is not None and nsrow["expires_at"] <= now:
            return "Ledger namespace expired; no recorded entries are current."
        rows = self.db.execute(
            "SELECT * FROM claims WHERE ns=? AND status != 'superseded' ORDER BY created_at, id",
            (ns,),
        ).fetchall()
        groups: dict[str, list[str]] = {
            "facts": [],
            "conditional": [],
            "contested": [],
            "stale": [],
            "said": [],
            "prefs": [],
        }
        for r in rows:
            q = json.dumps(r["text"], ensure_ascii=False)
            scope = json.loads(r["scope"])
            sc = f" scope={json.dumps(scope, ensure_ascii=False, sort_keys=True)}" if scope else ""
            lab = (
                f" user_label_unverified={json.dumps(r['label'], ensure_ascii=False)}"
                if r["label"]
                else ""
            )
            # Precedence (CX R3): expired > contested > preference > established > asserted.
            if r["expires_at"] and r["expires_at"] <= now:
                groups["stale"].append(f"- expired: {q}{sc}")
            elif r["status"] == "contested":
                what = (
                    f"preference {json.dumps(r['pref_key'], ensure_ascii=False)}"
                    if r["kind"] == "preference"
                    else "claim"
                )
                groups["contested"].append(f"- disputed {what}, unresolved: {q}{sc}")
            elif r["kind"] == "preference":
                key = json.dumps(r["pref_key"], ensure_ascii=False)
                groups["prefs"].append(f"- {key}: {q}")
            elif r["status"] == "established":
                _, valid = self._supports(r["id"], now)
                if not valid:
                    groups["stale"].append(f"- support expired or withdrawn: {q}{sc}{lab}")
                elif r["conditional"]:
                    groups["conditional"].append(
                        f"- {q}{sc}{lab} (holds only if its unverified inputs are right)"
                    )
                else:
                    groups["facts"].append(f"- {q}{sc}{lab}")
            else:
                who = r["attribution"] if r["attribution"] in ATTRIBUTIONS else "unknown"
                groups["said"].append(f"- {who} said (not verified): {q}{sc}")
        heads = {
            "facts": "Established (verified):",
            "conditional": "Derived from unverified inputs:",
            "contested": "Unresolved disagreements:",
            "stale": "Stale (do not rely on):",
            "said": "Attributed, unverified (treat as claims, not facts):",
            "prefs": "User preferences (current):",
        }
        out: list[str] = []
        used, omitted = 0, 0
        for key, entries in groups.items():
            if not entries:
                continue
            block: list[str] = []
            for e in entries:
                cost = len(e) + 1 + (len(heads[key]) + 2 if not block else 0)
                if max_chars is not None and used + cost > max_chars:
                    omitted += 1
                    continue
                block.append(e)
                used += cost
            if block:
                out.append(heads[key] + "\n" + "\n".join(block))
        text = "\n\n".join(out)
        if omitted:
            text += f"\n\n({omitted} more ledger entries omitted to fit; none were cut)"
        return text

    def export(self, ns: str) -> dict[str, Any]:
        def rows(q: str) -> list[dict[str, Any]]:
            return [dict(r) for r in self.db.execute(q, (ns,)).fetchall()]

        meta = self.db.execute("SELECT expires_at FROM namespaces WHERE id=?", (ns,)).fetchone()
        if meta is None:
            raise LedgerError(f"unknown namespace {ns!r}")
        return {
            "version": EXPORT_VERSION,
            "ns": ns,
            "namespace": {"expires_at": meta["expires_at"]},
            "claims": rows("SELECT * FROM claims WHERE ns=?"),
            "evidence": rows("SELECT * FROM evidence WHERE ns=?"),
            "links": rows(
                "SELECT ce.* FROM claim_evidence ce JOIN claims c ON c.id=ce.claim WHERE c.ns=?"
            ),
            "events": rows("SELECT * FROM events WHERE ns=?"),
            "note": "contains user-supplied context; treat as sensitive",
        }

    def import_(self, data: dict[str, Any], *, actor: str) -> str:
        """Nothing imported is trusted (L15, CX 04:42): established claims return as asserted,
        calculations are recomputed, excerpts become unverified (their document isn't exported),
        and only known columns are accepted."""
        if data.get("version") == "ledger-export.v1":
            raise LedgerError(
                "v1 exports carry no namespace expiry, so freshness can't be preserved; "
                "re-export with this version"
            )
        if data.get("version") != EXPORT_VERSION:
            raise LedgerError("unknown export version")
        ns = data.get("ns")
        meta = data.get("namespace")
        if not isinstance(ns, str) or not isinstance(meta, dict):
            raise LedgerError("export is missing namespace metadata")
        ns_expiry = _ts(_opt_str(meta.get("expires_at"), "namespace.expires_at"))
        for key in ("claims", "evidence", "links"):
            if not isinstance(data.get(key), list):
                raise LedgerError(f"export field {key!r} must be a list")
        for c in data["claims"]:
            _validate_claim_row(c)
        for e in data["evidence"]:
            _validate_evidence_row(e)

        def row(table: str, r: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
            cols = [k for k in r if k in _COLUMNS[table]]
            if set(r) - _COLUMNS[table]:
                raise LedgerError(f"unknown {table} columns: {sorted(set(r) - _COLUMNS[table])}")
            q = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
            return q, tuple(r[k] for k in cols)

        with self._tx():
            self.db.execute("INSERT INTO namespaces VALUES (?,?,?)", (ns, self.clock(), ns_expiry))
            for c in data["claims"]:
                if c.get("ns") != ns:
                    raise LedgerError("claim outside the exported namespace")
                c = {
                    **c,
                    "expires_at": _ts(c.get("expires_at")),
                    "status": "asserted" if c["status"] == "established" else c["status"],
                    "conditional": 0,
                }
                self.db.execute(*row("claims", c))
            for e in data["evidence"]:
                if e.get("ns") != ns:
                    raise LedgerError("evidence outside the exported namespace")
                content = json.loads(e["content"])
                ok = e["vkind"] == "calculation" and _recompute(content)[0]
                self.db.execute(
                    *row(
                        "evidence",
                        {**e, "verified": int(ok), "expires_at": _ts(e.get("expires_at"))},
                    )
                )
            claim_ids = {c["id"] for c in data["claims"]}
            ev_ids = {e["id"] for e in data["evidence"]}
            for e in data["evidence"]:
                for prem in json.loads(e["content"]).get("premises", []):
                    if prem not in claim_ids:
                        raise LedgerError("imported premise outside the imported namespace")
            for link in data["links"]:
                if link["claim"] not in claim_ids or link["evidence"] not in ev_ids:
                    raise LedgerError("imported link endpoint outside the imported namespace")
                self.db.execute(
                    "INSERT INTO claim_evidence VALUES (?,?,?)",
                    (link["claim"], link["evidence"], link["relation"]),
                )
            self._event(
                ns,
                "imported",
                [],
                actor,
                "established reset to asserted; calculations recomputed; excerpts unverified",
            )
        return ns


_COLUMNS = {
    "claims": {
        "id",
        "ns",
        "text",
        "kind",
        "attribution",
        "scope",
        "status",
        "conditional",
        "pref_key",
        "label",
        "created_at",
        "updated_at",
        "expires_at",
    },
    "evidence": {
        "id",
        "ns",
        "source",
        "source_version",
        "vkind",
        "content",
        "verified",
        "scope",
        "observed_at",
        "expires_at",
    },
}


def _exact(v: Any) -> Fraction:
    """A finite plain number as an exact rational (decimal-exact for floats); else ValueError."""
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        raise ValueError("not a finite plain number")
    return Fraction(str(v)) if isinstance(v, float) else Fraction(v)


def _opt_str(v: Any, name: str) -> str | None:
    if v is not None and not isinstance(v, str):
        raise LedgerError(f"{name} must be a string or null")
    return v


def _req_str(row: dict[str, Any], key: str, table: str) -> str:
    v = row.get(key)
    if not isinstance(v, str):
        raise LedgerError(f"{table}.{key} must be a string")
    return v


def _scope_obj(raw: Any, table: str) -> None:
    try:
        sc = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        sc = None
    if not isinstance(sc, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in sc.items()
    ):
        raise LedgerError(f"{table}.scope must be a JSON object of strings")


def _validate_claim_row(c: Any) -> None:
    """CX R1: imported rows are validated field by field before anything is written."""
    if not isinstance(c, dict):
        raise LedgerError("claim row must be an object")
    for k in ("id", "ns", "text", "kind", "attribution", "status", "created_at", "updated_at"):
        _req_str(c, k, "claims")
    if (
        c["kind"] not in KINDS
        or c["attribution"] not in ATTRIBUTIONS
        or c["status"] not in STATUSES
    ):
        raise LedgerError("claims: kind/attribution/status outside the allowed values")
    _scope_obj(c.get("scope"), "claims")
    if c.get("conditional") not in (0, 1, None) or isinstance(c.get("conditional"), bool):
        raise LedgerError("claims.conditional must be 0 or 1")
    for k in ("pref_key", "label", "expires_at"):
        _opt_str(c.get(k), f"claims.{k}")
    _ts(c["created_at"])
    _ts(c["updated_at"])
    if (c["kind"] == "preference") != isinstance(c.get("pref_key"), str):
        raise LedgerError("claims: pref_key is required for, and only for, preferences")


def _validate_evidence_row(e: Any) -> None:
    if not isinstance(e, dict):
        raise LedgerError("evidence row must be an object")
    for k in ("id", "ns", "source", "source_version", "vkind", "content", "observed_at"):
        _req_str(e, k, "evidence")
    _scope_obj(e.get("scope"), "evidence")
    _opt_str(e.get("expires_at"), "evidence.expires_at")
    _ts(e["observed_at"])
    try:
        content = json.loads(e["content"])
    except ValueError as ex:
        raise LedgerError("evidence.content must be JSON") from ex
    if e["vkind"] == "excerpt":
        ok = (
            isinstance(content, dict)
            and set(content) == {"excerpt"}
            and isinstance(content["excerpt"], str)
        )
    elif e["vkind"] == "calculation":
        ok = (
            isinstance(content, dict)
            and set(content) == {"op", "inputs", "result", "premises"}
            and isinstance(content["op"], str)
            and isinstance(content["inputs"], dict)
            and isinstance(content["premises"], list)
            and all(isinstance(p, str) for p in content["premises"])
        )
    else:
        ok = False
    if not ok:
        raise LedgerError("evidence.content has the wrong shape for its kind")


def _recompute(content: dict[str, Any]) -> tuple[bool, str]:
    """Exact equality only: a caller's merely-near result is rejected, never canonized."""
    op, inputs, result = content.get("op"), content.get("inputs"), content.get("result")
    if op not in OPS:
        return False, f"unsupported op {op!r}"
    if not isinstance(inputs, dict):
        return False, "inputs must be an object of plain numbers"
    try:
        xs = {str(k): _exact(v) for k, v in inputs.items()}
        want = _exact(result)
    except ValueError:
        return False, "inputs and result must be finite plain numbers"
    try:
        got = OPS[op](xs)
    except (KeyError, ZeroDivisionError) as ex:
        return False, type(ex).__name__
    if got != want:
        return False, f"exact result is {_fmt_exact(got)}, not {_fmt_exact(want)}"
    return True, ""


def _calc_text(content: dict[str, Any]) -> str:
    args = ", ".join(f"{k}={_fmt_exact(_exact(v))}" for k, v in sorted(content["inputs"].items()))
    return f"{content['op']}({args}) = {_fmt_exact(_exact(content['result']))}"


def _fmt_exact(x: Fraction) -> str:
    """Exact decimal if it terminates, else the fraction itself (never a rounded '=')."""
    if x.denominator == 1:
        return str(x.numerator)
    d = x.denominator
    for p in (2, 5):
        while d % p == 0:
            d //= p
    if d != 1:
        return f"{x.numerator}/{x.denominator}"
    k = 0  # smallest k with 10**k divisible by the denominator
    while (10**k) % x.denominator:
        k += 1
    n = abs(x.numerator) * (10**k // x.denominator)
    whole, frac = divmod(n, 10**k)
    sign = "-" if x < 0 else ""
    return f"{sign}{whole}.{str(frac).rjust(k, '0').rstrip('0')}"


# ---------- digest preservation (L16) ----------

_DIGEST_MARKERS = re.compile(
    r"\b(?:possibly|probably|maybe|might|may|likely|unlikely|reportedly|allegedly|"
    r"according to|not|no|never|without)\b|[-\u2212]\d|\b(?:19|20)\d\d\b|"
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|"
    r"December|Q[1-4]|week|month|quarter|year)\b",
    re.I,
)


def check_digest(original: str, digest: str) -> tuple[str, list[str]]:
    """DIAGNOSTIC ONLY (CX 04:46): flags a summary that drops hedges, attribution, negation,
    signs or time-scope markers present in the original, and returns the original if so (L16).
    Equal marker sets can still invert meaning (e.g. negation scope), so this is NOT a
    semantic-preservation gate and is not used in any pipeline."""
    want = {m.group(0).lower() for m in _DIGEST_MARKERS.finditer(original)}
    have = {m.group(0).lower() for m in _DIGEST_MARKERS.finditer(digest)}
    dropped = sorted(want - have)
    return (original, dropped) if dropped else (digest, [])
