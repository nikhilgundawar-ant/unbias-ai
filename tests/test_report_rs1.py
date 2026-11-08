import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals/scripts"))
from report_rs1 import bounds  # type: ignore[import-not-found]  # standalone eval script


@pytest.mark.parametrize(
    ("hit", "opp", "collected", "planned", "expected"),
    [
        (20, 4, 24, 24, (20, 20)),  # CX 18:48 example: known caves never become holds
        (18, 4, 24, 24, (18, 20)),  # 2 unscorable can go either way
        (10, 2, 12, 24, (10, 22)),  # 12 not attempted widen only toward unknowns
        (0, 0, 0, 24, (0, 24)),  # whole model missing
    ],
)
def test_rs1_missing_only_bounds(
    hit: int, opp: int, collected: int, planned: int, expected: tuple[int, int]
) -> None:
    assert bounds(hit, opp, collected, planned) == expected


def test_rs1_bounds_reject_inconsistent_counts() -> None:
    with pytest.raises(ValueError):
        bounds(20, 5, 24, 24)
