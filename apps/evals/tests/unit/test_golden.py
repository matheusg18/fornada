from pathlib import Path

import pytest

from fornada_evals.dataset import GoldenCase, load_cases

GOLDEN = Path(__file__).parents[2] / "datasets" / "golden.jsonl"


def full_day(case: GoldenCase) -> bool:
    # Days +3 and +4 are full in the seed.
    return "order_on_open_date" in case.metadata.checks and any(
        "{d+3:" in turn or "{d+4:" in turn for turn in case.turns
    )


# The final scenarios (AGENTS.md) that the deterministic layer can check.
FINAL_SCENARIOS = {
    "full day": full_day,
    "check_capacity down": lambda case: case.metadata.outage,
    "cake for 40 people": lambda case: case.metadata.party_size == 40,
    "flavor change after the quote": lambda case: case.metadata.flavor_change is not None,
}


def test_golden_dataset_loads() -> None:
    assert load_cases(GOLDEN)


@pytest.mark.parametrize("scenario", FINAL_SCENARIOS)
def test_final_scenario_has_a_critical_case(scenario: str) -> None:
    matches = FINAL_SCENARIOS[scenario]
    assert any(case.metadata.critical and matches(case) for case in load_cases(GOLDEN))
