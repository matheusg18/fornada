import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from fornada_evals.dataset import DatasetError, load_cases, render

RUN_DAY = dt.date(2026, 10, 21)  # a Wednesday


def case(**overrides: Any) -> dict[str, Any]:
    metadata = {
        "category": "DATE",
        "source": "#3",
        "critical": True,
        "checks": ["no_past_date"],
    }
    metadata.update(overrides.pop("metadata", {}))
    line = {
        "name": "date-wrong-year-27-10",
        "scenario": "Cliente pede bolo para 27/10 sem dizer o ano.",
        "expected_outcome": "Consulta a data no ano corrente.",
        "turns": [{"role": "user", "content": "Quero um bolo para {d+6:dd/mm}."}],
        "additional_metadata": metadata,
    }
    line.update(overrides)
    return line


def write(tmp_path: Path, *lines: dict[str, Any]) -> Path:
    path = tmp_path / "golden.jsonl"
    path.write_text("\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n")
    return path


class TestLoadCases:
    def test_complete_case_loads(self, tmp_path: Path) -> None:
        [loaded] = load_cases(write(tmp_path, case()))

        assert loaded.name == "date-wrong-year-27-10"
        assert loaded.turns == ["Quero um bolo para {d+6:dd/mm}."]
        assert loaded.metadata.category == "DATE"
        assert loaded.metadata.source == "#3"
        assert loaded.metadata.checks == ["no_past_date"]
        assert loaded.metadata.critical is True
        assert loaded.metadata.outage is False

    def test_missing_source_names_the_case(self, tmp_path: Path) -> None:
        line = case()
        del line["additional_metadata"]["source"]

        with pytest.raises(DatasetError, match=r"date-wrong-year-27-10.*source"):
            load_cases(write(tmp_path, line))

    def test_unknown_check_names_the_case_and_check(self, tmp_path: Path) -> None:
        line = case(metadata={"checks": ["no_past_date", "tone_is_friendly"]})

        with pytest.raises(DatasetError, match=r"date-wrong-year-27-10.*tone_is_friendly"):
            load_cases(write(tmp_path, line))

    def test_no_checks_fails(self, tmp_path: Path) -> None:
        with pytest.raises(DatasetError, match="checks"):
            load_cases(write(tmp_path, case(metadata={"checks": []})))

    def test_serving_rule_needs_a_party_size(self, tmp_path: Path) -> None:
        line = case(metadata={"category": "SIZE", "checks": ["serving_rule"]})

        with pytest.raises(DatasetError, match="party_size"):
            load_cases(write(tmp_path, line))

    def test_requote_needs_the_flavor_change(self, tmp_path: Path) -> None:
        line = case(metadata={"category": "PRICE", "checks": ["requote_after_change"]})

        with pytest.raises(DatasetError, match="flavor_change"):
            load_cases(write(tmp_path, line))

    def test_null_critical_mark_fails(self, tmp_path: Path) -> None:
        with pytest.raises(DatasetError, match=r"date-wrong-year-27-10.*critical"):
            load_cases(write(tmp_path, case(metadata={"critical": None})))

    def test_case_without_scenario_fails(self, tmp_path: Path) -> None:
        line = case()
        del line["scenario"]

        with pytest.raises(DatasetError, match="line 1"):
            load_cases(write(tmp_path, line))

    def test_assistant_turn_fails(self, tmp_path: Path) -> None:
        line = case(turns=[{"role": "assistant", "content": "Oi!"}])

        with pytest.raises(DatasetError, match="user"):
            load_cases(write(tmp_path, line))

    def test_duplicate_names_fail(self, tmp_path: Path) -> None:
        with pytest.raises(DatasetError, match="duplicate"):
            load_cases(write(tmp_path, case(), case()))


class TestRender:
    def test_day_month(self) -> None:
        assert render("quero um bolo para {d+3:dd/mm}", RUN_DAY) == "quero um bolo para 24/10"

    def test_day_month_year(self) -> None:
        assert render("{d+3:dd/mm/aaaa}", RUN_DAY) == "24/10/2026"

    def test_weekday(self) -> None:
        assert render("na {d+2:dia-semana}", RUN_DAY) == "na sexta-feira"

    def test_negative_offset(self) -> None:
        assert render("{d-2:dd/mm}", RUN_DAY) == "19/10"

    def test_crosses_the_year(self) -> None:
        assert render("{d+72:dd/mm/aaaa}", RUN_DAY) == "01/01/2027"

    def test_other_braces_are_left_alone(self) -> None:
        text = "bolo {de chocolate} e {d+3} e {x:dd/mm}"

        assert render(text, RUN_DAY) == text
