"""Exact multinomial audit of a proposed CI at the -0.02 noninferiority boundary.

No model calls. Enumerates all paired 2x2 tables with p(treatment-only)=0, rather than sampling.
The rejected candidate is frozen below for reproducibility, not production inference.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math


# Frozen rejected candidate from the 2026-11-08 review. Intentionally retained so later
# production changes cannot erase the reproduction. NEVER use this for efficacy decisions.
def _wilson(x: int, n: int, z: float) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = x / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, mid - half), min(1.0, mid + half)


def newcombe_paired_diff(
    both: int, only_treatment: int, only_baseline: int, neither: int, *, z: float = 1.959964
) -> tuple[float, float, float]:
    """Paired difference of proportions p_T - p_B with Newcombe (1998) method 10 (hybrid
    Wilson score with continuity-corrected phi). One binary outcome per family in each arm:
    `both` = event in both arms, `only_treatment` = event only under treatment, etc.

    Proposed boundary-aware alternative to the family bootstrap for single-probe binary
    endpoints (CX R4). With zero discordant families it still returns a non-degenerate
    interval, so 'no failures seen' is never mistaken for 'no failures possible'.
    PROSPECTIVE: not wired into release checks until CC/CX agree after simulation review.
    """
    a, b, c, d = both, only_treatment, only_baseline, neither
    n = a + b + c + d
    if n == 0 or min(a, b, c, d) < 0:
        raise ValueError("need non-negative counts with n > 0")
    p1, p2 = (a + b) / n, (a + c) / n
    l1, u1 = _wilson(a + b, n, z)
    l2, u2 = _wilson(a + c, n, z)
    den = (a + b) * (c + d) * (a + c) * (b + d)
    if den == 0:
        phi = 0.0
    else:
        raw = a * d - b * c
        num = max(raw - n / 2, 0.0) if raw > 0 else float(raw)  # Newcombe's continuity correction
        phi = num / math.sqrt(den)
    delta = math.sqrt(max(0.0, (p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2))
    eps = math.sqrt(max(0.0, (u1 - p1) ** 2 - 2 * phi * (u1 - p1) * (p2 - l2) + (p2 - l2) ** 2))
    diff = p1 - p2
    return diff, max(-1.0, diff - delta), min(1.0, diff + eps)


def audit(n: int, both_p: float, baseline_only_p: float) -> dict[str, object]:
    neither_p = 1 - both_p - baseline_only_p
    total = covered = false_ni = 0.0
    log_factorials = [math.lgamma(i + 1) for i in range(n + 1)]
    truth = -baseline_only_p
    for both in range(n + 1):
        for baseline_only in range(n - both + 1):
            neither = n - both - baseline_only
            log_p = (
                log_factorials[n]
                - log_factorials[both]
                - log_factorials[baseline_only]
                - log_factorials[neither]
                + both * math.log(both_p)
                + baseline_only * math.log(baseline_only_p)
                + neither * math.log(neither_p)
            )
            probability = math.exp(log_p)
            _, lo, hi = newcombe_paired_diff(both, 0, baseline_only, neither)
            total += probability
            if lo - 1e-12 <= truth <= hi + 1e-12:
                covered += probability
            if lo > -0.02:
                false_ni += probability
    return {
        "n_independent_pairs": n,
        "joint_probabilities_both_treatment_only_baseline_only_neither": [
            both_p,
            0,
            baseline_only_p,
            neither_p,
        ],
        "true_risk_difference": truth,
        "enumerated_mass": total,
        "coverage": covered,
        "false_noninferiority_probability_at_boundary": false_ni,
        "nominal_interval": 0.95,
        "nominal_one_sided_false_pass_target": 0.025,
    }


if __name__ == "__main__":
    source = inspect.getsource(newcombe_paired_diff) + inspect.getsource(_wilson)
    print(
        json.dumps(
            {
                "candidate_source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "method": "exact enumeration of multinomial tables; floating-point arithmetic",
                "results": [audit(200, 0.49, 0.02), audit(200, 0.96, 0.02)],
            },
            indent=2,
        )
    )
