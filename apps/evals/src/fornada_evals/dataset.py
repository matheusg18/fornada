"""The golden dataset: JSONL in DeepEval's `ConversationalGolden` shape, validated on load.

Each case's `additional_metadata` ties it to the phase 3 taxonomy (category and source
conversation) and says which checks apply, whether it gates on pass^3 and any setup.
Customer turns write dates relative to the run day; `render` fills them in when the case runs.
"""

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from deepeval.dataset import ConversationalGolden, EvaluationDataset
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

# The taxonomy's categories (docs/error-analysis/phase-3-taxonomy.md, section 3).
type Category = Literal[
    "DATE", "CAPACITY", "OUTAGE", "MESSAGE", "ESCALATION", "ALLERGEN", "SIZE", "PRICE", "POLICY"
]

# One id per check in `fornada_evals.checks`; its registry is keyed by exactly these.
type CheckId = Literal[
    "no_past_date",
    "order_on_open_date",
    "no_order_after_outage",
    "price_from_tool",
    "escalation_has_phone",
    "serving_rule",
    "confirmation_before_order",
    "requote_after_change",
    "no_message_to_owner",
]


class DatasetError(ValueError):
    """A golden case that cannot run; the message names the case."""


class FlavorChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    turn: int = Field(ge=1)  # 1-based customer turn where the flavor changes
    product: str = Field(min_length=1)  # the new product's slug


class CaseMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: Category
    source: str = Field(pattern=r"^#\d+$")  # the conversation's number in the open codes
    critical: bool
    checks: list[CheckId] = Field(min_length=1)
    outage: bool = False
    party_size: int | None = Field(default=None, gt=0)
    flavor_change: FlavorChange | None = None

    @field_validator("critical", mode="before")
    @classmethod
    def _critical_is_marked(cls, value: object) -> object:
        if value is None:
            raise ValueError("must be true or false; the maintainer marks each case")
        return value

    @model_validator(mode="after")
    def _setup_for_checks(self) -> "CaseMetadata":
        if "serving_rule" in self.checks and self.party_size is None:
            raise ValueError("serving_rule needs party_size")
        if "requote_after_change" in self.checks and self.flavor_change is None:
            raise ValueError("requote_after_change needs flavor_change")
        return self


@dataclass(frozen=True)
class GoldenCase:
    name: str
    scenario: str
    expected_outcome: str | None
    turns: list[str]  # customer turns, placeholders not yet rendered
    metadata: CaseMetadata


def load_cases(path: Path) -> list[GoldenCase]:
    """Load and validate every case; the first bad one raises `DatasetError`."""
    _require_scenarios(path)
    dataset = EvaluationDataset()
    dataset.add_goldens_from_jsonl_file(str(path))
    cases: list[GoldenCase] = []
    names: set[str] = set()
    for line, golden in enumerate(dataset.goldens, start=1):
        if not isinstance(golden, ConversationalGolden):
            raise DatasetError(f"line {line}: not a conversational case (no scenario)")
        if not golden.name:
            raise DatasetError(f"line {line}: case has no name")
        label = f"case {golden.name!r}"
        if golden.name in names:
            raise DatasetError(f"{label}: duplicate name")
        names.add(golden.name)
        turns = golden.turns or []
        if not turns or any(turn.role != "user" for turn in turns):
            raise DatasetError(f"{label}: turns must be one or more user turns")
        try:
            metadata = CaseMetadata.model_validate(golden.additional_metadata or {})
        except ValidationError as error:
            raise DatasetError(f"{label}: {_describe(error)}") from error
        cases.append(
            GoldenCase(
                name=golden.name,
                scenario=golden.scenario,
                expected_outcome=golden.expected_outcome,
                turns=[turn.content for turn in turns],
                metadata=metadata,
            )
        )
    return cases


def _require_scenarios(path: Path) -> None:
    # DeepEval reads a line without `scenario` as a single-turn golden and fails on its
    # missing `input`, without naming the line; catch it first.
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for number, line in enumerate(lines, start=1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise DatasetError(f"line {number}: invalid JSON ({error.msg})") from error
        if not isinstance(entry, dict) or not entry.get("scenario"):
            name = entry.get("name") if isinstance(entry, dict) else None
            raise DatasetError(f"line {number} ({name!r}): no scenario")


def _describe(error: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(map(str, e['loc'])) or 'metadata'}: {e['msg']} (got {e['input']!r})"
        for e in error.errors()
    )


_PLACEHOLDER = re.compile(r"\{d([+-]\d+):(dd/mm/aaaa|dd/mm|dia-semana)\}")
_WEEKDAYS = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)


def render(text: str, run_day: dt.date) -> str:
    """Replace `{d+N:dd/mm}`, `{d+N:dd/mm/aaaa}` and `{d+N:dia-semana}` with the date N
    days from `run_day`. Any other braces are customer text and stay as they are."""

    def replace(match: re.Match[str]) -> str:
        day = run_day + dt.timedelta(days=int(match[1]))
        match match[2]:
            case "dd/mm":
                return day.strftime("%d/%m")
            case "dd/mm/aaaa":
                return day.strftime("%d/%m/%Y")
            case _:
                return _WEEKDAYS[day.weekday()]

    return _PLACEHOLDER.sub(replace, text)
