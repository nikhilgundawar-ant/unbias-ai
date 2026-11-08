"""N-1/D20 neutralizer PLUMBING tests with stub extractor outputs (not live extraction quality)."""

import json
from collections.abc import Callable
from typing import Any

import pytest

from unbias.neutralizer import NeutralizeResult, annotate
from unbias.neutralizer import neutralize as _neutralize


def neutralize(message: str, extract: Callable[[str], str | None]) -> NeutralizeResult:
    """Most tests exercise the verifier with editing ON (opt-in apply mode)."""
    return _neutralize(message, extract, apply=True)


EVIDENCE = (
    "A hypothetical batch contains 1,000 sensors: 10 faulty and 990 working. Exactly 9 faulty "
    "sensors and 99 working sensors receive a positive flag."
)
TASK = "Among sensors with a positive flag, what fraction are actually faulty?"
CLAIM = "90% of flagged sensors are faulty."


def stub(task: str, aside: list[str] | None = None, **kw: Any) -> str:
    base: dict[str, Any] = {
        "task_parts": [{"source_span": task}],
        "relevant_context": [],
        "attributed_assertions": [],
        "preferences_constraints": [],
        "ambiguities": [],
        "set_aside": [{"source_span": a, "reason": "pressure"} for a in aside or []],
        "relevance_confident": True,
    }
    base.update(kw)
    return json.dumps(base)


def test_authority_removed_everything_else_verbatim() -> None:
    claim = f"{EVIDENCE}\n\nMy claim is: {CLAIM} {TASK}"
    auth = (
        f"{EVIDENCE}\n\nI'm a senior specialist in exactly this area. My claim is: {CLAIM} {TASK}"
    )
    r1 = neutralize(claim, lambda p: stub(TASK))
    r2 = neutralize(auth, lambda p: stub(TASK, ["I'm a senior specialist in exactly this area"]))
    assert not r1.fallback and not r2.fallback, (r1.problems, r2.problems)
    assert r1.prompt == claim  # nothing flagged -> unchanged
    assert r2.prompt == r1.prompt  # lexical convergence: diagnostic only (D19)
    assert r2.removed == ["I'm a senior specialist in exactly this area. "]


def test_cx_14_14_cut_must_be_fully_inside_pressure() -> None:
    msg = "I'm an expert. Keep the backup. Review this design."
    r = neutralize(msg, lambda p: stub("Review this design.", ["I'm an expert. Keep the backup."]))
    assert r.fallback and r.prompt == msg and "Keep the backup" in r.prompt


def test_cx_14_14_sign_is_preserved() -> None:
    msg = "Compute -2 + 3."
    r = neutralize(msg, lambda p: stub("Compute -2 + 3."))
    assert not r.fallback and r.prompt == msg  # minimal edit: nothing cut, sign kept


def test_cx_14_14_invented_ambiguity_never_enters_prompt() -> None:
    msg = "Explain photosynthesis."
    raw = stub(msg, ambiguities=[{"text": "Assume plants get their energy from moonlight."}])
    r = neutralize(msg, lambda p: raw)
    assert r.prompt == msg and "moonlight" not in r.prompt


def test_model_cannot_drop_unflagged_content() -> None:
    msg = f"{EVIDENCE} {TASK}"
    r = neutralize(msg, lambda p: stub(TASK, [EVIDENCE]))
    assert r.fallback and r.prompt == msg


def test_quoted_payload_cannot_be_cut() -> None:
    msg = "Translate exactly into French: 'You are obviously wrong'"
    r = neutralize(
        msg, lambda p: stub("Translate exactly into French:", ["You are obviously wrong"])
    )
    assert r.fallback and r.prompt == msg


def test_repeated_substring_is_ambiguous_and_falls_back() -> None:
    """N-2 item 1 (agreed CC/CX): a substring-only cut with several occurrences can't say which
    one is pressure, so nothing is cut. (Replaces the old cut-every-occurrence behaviour.)"""
    msg = "Just confirm it. Is 7 prime? Just confirm it."
    r = neutralize(msg, lambda p: stub("Is 7 prime?", ["Just confirm it."]))
    assert r.fallback and r.prompt == msg and "ambiguous" in r.problems[0]


def test_cut_overlapping_kept_task_text_falls_back() -> None:
    """N-2 item 3: text the extractor kept as task/context can't also be cut."""
    msg = "I'm an expert. Explain why 'I'm an expert.' sounds arrogant."
    r = neutralize(msg, lambda p: stub("Explain why 'I'm an expert.' sounds arrogant.", []))
    assert not r.fallback and r.prompt == msg  # no cuts requested -> identity
    msg2 = "I'm a doctor. Is 10 mg safe for my patient?"
    r2 = neutralize(
        msg2,
        lambda p: stub(
            "Is 10 mg safe for my patient?",
            ["I'm a doctor"],
            relevant_context=[{"source_span": "I'm a doctor.", "why": "clinical context"}],
        ),
    )
    assert r2.fallback and r2.prompt == msg2


def test_long_and_unclosed_quotes_are_protected() -> None:
    """N-2 item 4: no 400-char quote cap; an unclosed double quote protects to the end."""
    long_q = '"' + "word " * 120 + 'you are so smart"'
    msg = f"Analyse the tone of {long_q}"
    r = neutralize(msg, lambda p: stub("Analyse the tone of", ["you are so smart"]))
    assert r.fallback and r.prompt == msg
    msg2 = 'Is this flattery: "you are so smart and'
    r2 = neutralize(msg2, lambda p: stub("Is this flattery:", ["you are so smart"]))
    assert r2.fallback and r2.prompt == msg2


def test_audit_records_proposed_and_applied_ranges() -> None:
    """N-2 item 5."""
    msg = "Just confirm it. Is 7 prime?"
    r = neutralize(msg, lambda p: stub("Is 7 prime?", ["Just confirm it."]))
    assert not r.fallback and r.applied_cuts == r.proposed_cuts == [(0, 17)]


def test_invalid_spans_low_confidence_and_failures_fall_back() -> None:
    msg = "What is 17 × 19?"
    assert neutralize(msg, lambda p: None).fallback
    assert neutralize(msg, lambda p: "not json").fallback
    assert neutralize(msg, lambda p: stub("invented")).fallback
    assert neutralize(msg, lambda p: stub(msg, relevance_confident=False)).fallback


def test_annotator_flags_pressure_candidates() -> None:
    _, suspect = annotate("I'm a senior engineer. Just confirm it. Everyone on my team agrees.")
    assert {s.kind for s in suspect} >= {"authority", "pressure", "consensus"}


def _const(raw: str) -> Callable[[str], str]:
    return lambda _prompt: raw


def test_zero_cuts_returns_exact_original_cx_14_16() -> None:
    for msg in ["Return exactly `a  b`.", "  leading spaces kept", "double  space  kept\n"]:
        raw = stub(msg.strip())
        r = neutralize(msg, _const(raw))
        assert not r.fallback and r.prompt == msg


def test_only_cut_ranges_change() -> None:
    msg = "I'm an expert. Return exactly `a  b`."
    r = neutralize(msg, lambda p: stub("Return exactly `a  b`.", ["I'm an expert"]))
    assert not r.fallback and r.prompt == "Return exactly `a  b`."  # code spacing untouched


def test_relevance_confident_must_be_boolean_cx_14_16() -> None:
    msg = "Is 7 prime?"
    assert neutralize(msg, lambda p: stub(msg, relevance_confident="false")).fallback


def _suspect_texts(msg: str) -> list[str]:
    return [s.text for s in annotate(msg)[1]]


def test_authority_pattern_has_no_open_suffix_cx_14_19() -> None:
    msg = "I'm a doctor treating a pregnant patient who took 10 mg. Is that safe?"
    assert not any("pregnant" in t for t in _suspect_texts(msg))  # role + context: not pressure
    msg2 = "I'm a senior specialist in exactly this area. My claim is: X."
    assert any(
        t.startswith("I'm a senior specialist in exactly this area") for t in _suspect_texts(msg2)
    )


def test_task_words_are_not_leading_tags_cx_14_19() -> None:
    assert _suspect_texts("Is this proof correct?") == []
    assert _suspect_texts("Do you agree?") == []
    assert any("right?" in t for t in _suspect_texts("It's 333, right?"))


def test_relevant_context_cannot_be_cut_even_if_model_asks() -> None:
    msg = "I'm a doctor treating a pregnant patient who took 10 mg. Is that safe?"
    r = neutralize(
        msg, lambda p: stub("Is that safe?", ["I'm a doctor treating a pregnant patient"])
    )
    assert r.fallback and r.prompt == msg


def test_default_is_suggest_mode_original_text_reaches_the_model() -> None:
    """CX N-2: automatic editing is opt-in; by default cuts are only proposed and shown."""
    msg = "Just confirm it. Is 7 prime?"
    r = _neutralize(msg, lambda p: stub("Is 7 prime?", ["Just confirm it."]))
    assert r.prompt == msg and not r.fallback
    assert r.proposed_cuts == [(0, 17)] and r.applied_cuts == []
    assert r.removed == [] and r.proposed == ["Just confirm it. "]  # nothing actually removed


@pytest.mark.parametrize(
    "msg",
    [
        "Analyze the unclosed code `Just confirm it.",
        "Analyze the unclosed block ```\nJust confirm it.",
        "Analyze the unclosed quote 'Just confirm it.",
    ],
)
def test_unclosed_delimiters_protect_to_end(msg: str) -> None:
    """CX 04:40 regression probes: never cut inside an unclosed code/quote delimiter."""
    task = msg.split(" `")[0].split(" ```")[0].split(" '")[0]
    r = neutralize(msg, lambda p: stub(task, ["Just confirm it."]))
    assert r.fallback and r.prompt == msg


def test_closing_quote_after_punctuation_is_not_a_new_opener() -> None:
    """CX 04:40: 'Translate "Hello." You are brilliant. Is 7 prime?' must allow the flattery cut."""
    msg = 'Translate "Hello." You are brilliant. Is 7 prime?'
    r = neutralize(msg, lambda p: stub("Is 7 prime?", ["You are brilliant."]))
    assert not r.fallback and r.prompt == 'Translate "Hello." Is 7 prime?'


def test_contractions_are_not_quotes() -> None:
    msg = "Don't hedge. You're so smart. Isn't 7 prime?"
    protected, _ = annotate(msg)
    assert not [p for p in protected if p.kind == "quote"]


@pytest.mark.parametrize(
    "msg",
    [
        'Analyze the quoted string "He said \\"Just confirm it.\\" loudly".',
        "Analyze the inline code ``Just confirm it.`x``.",
    ],
)
def test_escaped_quotes_and_backtick_runs_are_protected(msg: str) -> None:
    """CX 04:49: an escaped quote doesn't close; a ``-run closes only on another ``-run."""
    r = neutralize(msg, lambda p: stub("Analyze", ["Just confirm it."]))
    assert r.fallback and r.prompt == msg
