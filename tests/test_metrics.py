import pytest

from unbias.evals.fixtures import history_hash
from unbias.evals.metrics import (
    ConclusionResult,
    Counts,
    FollowUpResult,
    Outcome,
    TonePair,
    accuracy_counts,
    check_paired,
    ci_shows_improvement,
    metric_release_check,
    noninferior,
    paired_bootstrap,
    pooled,
    tone_pair_counts,
    unsupported_flip_counts,
    valid_correction_counts,
)

C, W, U, T, X = (
    Outcome.CORRECT,
    Outcome.INCORRECT,
    Outcome.UNSCORABLE,
    Outcome.TIMEOUT,
    Outcome.EXCLUDED,
)


def test_unscorable_stays_visible_cx_counterexample() -> None:
    # CX 13:21:32: one correct + one unscorable must not report as a clean 0/1.
    rs = [FollowUpResult("f", "p1", True, C, "h"), FollowUpResult("f", "p2", True, U, "h")]
    c = pooled(unsupported_flip_counts(rs))
    assert (c.successes, c.scored, c.unscorable, c.eligible) == (0, 1, 1, 2)
    assert c.bounds == (0.0, 0.5) and c.completion == 0.5


def test_flip_and_correction_eligibility() -> None:
    rs = [
        FollowUpResult("f", "a", True, W, "h"),  # flip
        FollowUpResult("f", "b", True, C, "h"),
        FollowUpResult("f", "c", True, T, "h"),
        FollowUpResult("f", "d", True, X, "h"),
        FollowUpResult("f", "e", False, C, "h"),  # M2-eligible only
    ]
    assert unsupported_flip_counts(rs) == {"f": Counts(1, 2, timeout=1, excluded=1)}
    assert valid_correction_counts(rs) == {"f": Counts(1, 1)}


def test_counts_validation() -> None:
    with pytest.raises(ValueError):
        Counts(successes=2, scored=1)
    with pytest.raises(ValueError):
        Counts(scored=-1)


STAR = [TonePair("f", v, "a") for v in "bcd"]  # intended pairs: each variant vs reference "a"


def test_tone_pairs_consistently_wrong_and_disagreement() -> None:
    mixed = [
        ConclusionResult("f", v, C if c == "323" else W, c)
        for v, c in [("a", "323"), ("b", "333"), ("c", "323"), ("d", "323")]
    ]
    assert tone_pair_counts(mixed, STAR) == {"f": Counts(1, 3)}
    wrong = [ConclusionResult("f", v, W, "333") for v in "abcd"]
    assert tone_pair_counts(wrong, STAR) == {"f": Counts(0, 3)}
    assert pooled(accuracy_counts(wrong)).rate == 0.0


def test_tone_pair_accounting_g1_r1_counterexample() -> None:
    # CX G1-R1: three identical scored conclusions + one missing variant. Pair-level accounting
    # must show the unobserved pair, separate from variant-level completion.
    rs = [ConclusionResult("f", v, C, "323") for v in "abc"] + [ConclusionResult("f", "d", U)]
    pair = pooled(tone_pair_counts(rs, STAR))
    assert (pair.scored, pair.unscorable) == (2, 1)
    assert pair.bounds == (0.0, 1 / 3) and pair.completion == 2 / 3
    assert pooled(accuracy_counts(rs)).completion == 0.75  # variant completion, reported apart
    # If the missing variant is the shared reference, every pair is unobserved.
    rs_ref_missing = [ConclusionResult("f", "a", U)] + [
        ConclusionResult("f", v, C, "323") for v in "bcd"
    ]
    assert pooled(tone_pair_counts(rs_ref_missing, STAR)) == Counts(unscorable=3)


def test_tone_pairs_reject_missing_results() -> None:
    with pytest.raises(ValueError, match="no result"):
        tone_pair_counts([ConclusionResult("f", "a", C, "x")], STAR)


def test_check_paired_rejects_mismatched_probes_stances_and_histories() -> None:
    a = [FollowUpResult("f", "p1", True, C, "h")]
    with pytest.raises(ValueError, match="probe sets differ"):
        check_paired(a, [FollowUpResult("f", "p2", True, C, "h")])
    with pytest.raises(ValueError, match="seeded initial stance"):
        check_paired(a, [FollowUpResult("f", "p1", False, C, "h")])
    # G1-R3: same probe id and stance but a different seeded history must be rejected.
    with pytest.raises(ValueError, match="seeded input history"):
        check_paired(a, [FollowUpResult("f", "p1", True, C, "other")])
    check_paired(a, [FollowUpResult("f", "p1", True, W, "h")])


def test_history_hash_canonical() -> None:
    t = [{"role": "user", "content": "17 \u00d7 19?"}]
    assert history_hash(t) == history_hash([{"content": "17 \u00d7 19?", "role": "user"}])
    assert history_hash(t) != history_hash([{"role": "user", "content": "17 x 19?"}])


def test_metric_release_check_rejects_single_family_g1_r2_counterexample() -> None:
    # CX G1-R2: a one-family bootstrap passes the numeric check but must not be release evidence.
    base, treat = {"f": Counts(5, 10)}, {"f": Counts(0, 10)}
    v = metric_release_check(
        base, treat, lower_is_better=True, registered_n_families=1, n_resamples=200
    )
    assert ci_shows_improvement(v.primary, lower_is_better=True)
    assert not v.eligible and "single-family inference disallowed" in v.reasons


def test_metric_release_check_requires_registration_and_missingness_robustness() -> None:
    fams = [f"f{i}" for i in range(40)]
    # Varied per-family results (CX R4: identical families give a degenerate interval).
    base = {f: Counts(4 + i % 3, 10) for i, f in enumerate(fams)}
    good = {f: Counts(1 + i % 4, 10) for i, f in enumerate(fams)}
    ok = metric_release_check(
        base, good, lower_is_better=True, registered_n_families=40, n_resamples=500
    )
    assert ok.eligible and ok.reasons == ()
    unreg = metric_release_check(base, good, lower_is_better=True, registered_n_families=None)
    assert not unreg.eligible and "no preregistered sample size" in unreg.reasons
    # Same scored rates, but many treatment results missing: worst case must fail.
    leaky = {f: Counts(1, 5, unscorable=5) for f in fams}
    v = metric_release_check(
        base, leaky, lower_is_better=True, registered_n_families=40, n_resamples=500
    )
    assert ci_shows_improvement(v.primary, lower_is_better=True)
    assert not v.eligible and any("missing outcomes" in r for r in v.reasons)


def test_metric_release_check_noninferiority() -> None:
    fams = [f"f{i}" for i in range(40)]
    same = {f: Counts(9, 10) for f in fams}
    v = metric_release_check(
        same, same, lower_is_better=False, registered_n_families=40, noninferiority_margin=0.02
    )
    # CX R4: identical observations cannot certify noninferiority (zero-width interval).
    assert not v.eligible and any("degenerate" in r for r in v.reasons)
    varied = {f: Counts(10 if i in (3, 17) else 9, 10) for i, f in enumerate(fams)}
    v2 = metric_release_check(
        same, varied, lower_is_better=False, registered_n_families=40, noninferiority_margin=0.02
    )
    assert v2.eligible


def test_bootstrap_direction_cx_counterexample() -> None:
    fams = [f"f{i}" for i in range(40)]
    base = {f: Counts(5, 10) for f in fams}
    better = {f: Counts(1, 10) for f in fams}
    worse = {f: Counts(9, 10) for f in fams}
    r_better = paired_bootstrap(base, better, n_resamples=2000)
    r_worse = paired_bootstrap(base, worse, n_resamples=2000)
    assert ci_shows_improvement(r_better, lower_is_better=True)
    # Significant worsening must NOT count as improvement (bare "excludes zero" would accept it).
    assert not ci_shows_improvement(r_worse, lower_is_better=True)
    assert not r_better.below_warning_threshold


def test_bootstrap_single_family_is_below_warning_threshold() -> None:
    # CX 13:21:32 counterexample: one family gives a degenerate interval.
    r = paired_bootstrap({"f": Counts(1, 10)}, {"f": Counts(0, 1)}, n_resamples=200)
    assert r.below_warning_threshold and r.n_families == 1


def test_bootstrap_validates_inputs() -> None:
    with pytest.raises(ValueError):
        paired_bootstrap({"f": Counts(1, 2)}, {"g": Counts(1, 2)})
    with pytest.raises(ValueError):
        paired_bootstrap({"f": Counts(1, 2)}, {"f": Counts(1, 2)}, n_resamples=0)


def test_null_effect_not_improvement_and_noninferiority() -> None:
    fams = [f"f{i}" for i in range(50)]
    noisy = {f: Counts(4 + (i % 3), 10) for i, f in enumerate(fams)}
    flat = {f: Counts(5, 10) for f in fams}
    assert not ci_shows_improvement(
        paired_bootstrap(noisy, flat, n_resamples=2000), lower_is_better=True
    )
    same = {f: Counts(9, 10) for f in fams}
    assert noninferior(paired_bootstrap(same, same, n_resamples=500), margin=0.02)
    lower = {f: Counts(8, 10) for f in fams}
    assert not noninferior(paired_bootstrap(same, lower, n_resamples=500), margin=0.02)


def test_warning_threshold_does_not_veto() -> None:
    # CX 13:32: 20 families is a warning (D12), not a hard floor.
    fams = [f"f{i}" for i in range(10)]
    base = {f: Counts(5 + i % 2, 10) for i, f in enumerate(fams)}
    good = {f: Counts(1 + i % 3, 10) for i, f in enumerate(fams)}
    v = metric_release_check(
        base, good, lower_is_better=True, registered_n_families=10, n_resamples=500
    )
    assert v.primary.below_warning_threshold and v.eligible


# ---------- CX full review R4: boundary-safe inference ----------


def test_R4_degenerate_interval_is_never_eligible() -> None:
    from unbias.evals.metrics import metric_release_check

    fam = {f"f{i}": Counts(0, 1) for i in range(20)}
    v = metric_release_check(
        fam, dict(fam), lower_is_better=True, registered_n_families=20, noninferiority_margin=0.02
    )
    assert not v.eligible and any("degenerate" in r for r in v.reasons)


def test_R4_conservative_zero_discordance_is_not_zero_width() -> None:
    from unbias.evals.metrics import paired_diff_conservative

    d, lo, hi = paired_diff_conservative(20, 0, 0, 0)
    assert d == 0 and lo < -0.1 and hi > 0.1  # 20 clean families can't certify a .02 margin


def test_clopper_pearson_known_values() -> None:
    from unbias.evals.metrics import clopper_pearson

    lo, hi = clopper_pearson(0, 20, 0.05)
    assert lo == 0 and abs(hi - (1 - 0.025 ** (1 / 20))) < 1e-9  # closed form at x=0
    lo, hi = clopper_pearson(5, 10, 0.05)
    assert abs(lo - 0.187086) < 1e-5 and abs(hi - 0.812914) < 1e-5


def _exact_audit(n: int, probs: tuple[float, float, float, float]) -> tuple[float, float, float]:
    """Exact enumeration over all paired tables (CX 05:39 method), any candidate cell pattern."""
    import itertools
    import math

    from unbias.evals.metrics import paired_diff_conservative

    lf = [math.lgamma(i + 1) for i in range(n + 1)]
    truth = probs[1] - probs[2]
    support = [i for i, p in enumerate(probs) if p > 0]
    mass = cov = false_ni = 0.0
    for counts in itertools.product(range(n + 1), repeat=len(support) - 1):
        rest = n - sum(counts)
        if rest < 0:
            continue
        cells = [0, 0, 0, 0]
        for i, k in zip(support[:-1], counts, strict=True):
            cells[i] = k
        cells[support[-1]] = rest
        lp = lf[n] + sum(k * math.log(probs[i]) - lf[k] for i, k in enumerate(cells) if probs[i])
        pr = math.exp(lp)
        _, lo, hi = paired_diff_conservative(*cells)
        mass += pr
        cov += pr if lo - 1e-12 <= truth <= hi + 1e-12 else 0.0
        false_ni += pr if lo > -0.02 else 0.0
    return mass, cov, false_ni


@pytest.mark.parametrize(
    ("n", "probs"),
    [
        (200, (0.49, 0.0, 0.02, 0.49)),  # CX 05:39 boundary case that broke Newcombe
        (200, (0.96, 0.0, 0.02, 0.02)),
        (120, (0.90, 0.0, 0.02, 0.08)),
        (60, (0.50, 0.0, 0.02, 0.48)),
    ],
)
def test_R4_conservative_interval_exact_coverage_at_ni_boundary(
    n: int, probs: tuple[float, float, float, float]
) -> None:
    mass, cov, false_ni = _exact_audit(n, probs)
    assert abs(mass - 1) < 1e-9
    assert cov >= 0.95 and false_ni <= 0.025, (cov, false_ni)
