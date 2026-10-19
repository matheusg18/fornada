import re

import pytest

from fornada_simulator.personas import MALANDRO, PERSONAS
from fornada_simulator.scenarios import (
    COMPLICATIONS,
    INTENTS,
    Cell,
    UnknownComplicationError,
    plan_matrix,
)

from .test_personas import FORBIDDEN

INTENT = {intent.id: intent for intent in INTENTS}
COMPLICATION = {complication.id: complication for complication in COMPLICATIONS}


def goals_with(complication_id: str) -> list[str]:
    return [Cell(PERSONAS[0], intent, COMPLICATION[complication_id]).goal for intent in INTENTS]


def test_five_distinct_intents_and_complications() -> None:
    assert [i.id for i in INTENTS] == [
        "retirada",
        "entrega",
        "orcamento",
        "duvida_cardapio",
        "pos_pedido",
    ]
    assert [c.id for c in COMPLICATIONS] == [
        "nenhuma",
        "data_lotada",
        "troca_sabor",
        "ferramenta_fora",
        "tamanho_ambiguo",
    ]


def test_texts_do_not_reveal_the_test() -> None:
    for text in (*(i.text for i in INTENTS), *(c.text for c in COMPLICATIONS)):
        assert not FORBIDDEN.search(text), text


def test_control_adds_nothing() -> None:
    for intent in INTENTS:
        assert Cell(PERSONAS[0], intent, COMPLICATION["nenhuma"]).goal == intent.text


def test_same_cell_same_goal() -> None:
    def build() -> str:
        return Cell(PERSONAS[1], INTENT["entrega"], COMPLICATION["troca_sabor"]).goal

    goal = build()
    assert goal == build()
    assert INTENT["entrega"].text in goal
    assert "mude de ideia sobre o sabor" in goal


def test_full_date_asks_for_three_days_ahead() -> None:
    for goal in goals_with("data_lotada"):
        assert "daqui a 3 dias" in goal


def test_outage_names_a_date_and_no_failure() -> None:
    for goal in goals_with("ferramenta_fora"):
        assert "daqui a 6 dias" in goal
        assert not re.search(r"sistema|fora do ar|falh|indispon|erro|problema", goal, re.I)


def test_flavor_change_and_ambiguous_size_keep_their_anchors() -> None:
    for goal in goals_with("troca_sabor"):
        assert "mude de ideia sobre o sabor" in goal
    for goal in goals_with("tamanho_ambiguo"):
        assert "não fale em quilos" in goal
        assert "40 pessoas" in goal


def test_cheater_cells_use_no_legacy_goal() -> None:
    for cell in plan_matrix([c.id for c in COMPLICATIONS]):
        if cell.persona is MALANDRO:
            assert all(legacy not in cell.goal for legacy in MALANDRO.goals)


def test_full_matrix_has_125_distinct_cells() -> None:
    cells = plan_matrix([c.id for c in COMPLICATIONS])
    assert len(cells) == 125
    assert len({cell.key for cell in cells}) == 125
    for persona in PERSONAS:
        assert sum(cell.persona is persona for cell in cells) == 25


def test_default_leaves_the_outage_out() -> None:
    cells = plan_matrix()
    assert len(cells) == 100
    assert all(cell.complication.id != "ferramenta_fora" for cell in cells)


def test_outage_only() -> None:
    cells = plan_matrix(["ferramenta_fora"])
    assert len(cells) == 25
    assert {cell.complication.id for cell in cells} == {"ferramenta_fora"}


def test_first_five_cells_cover_every_persona() -> None:
    assert {cell.persona.id for cell in plan_matrix()[:5]} == {p.id for p in PERSONAS}


def test_unknown_complication_is_named() -> None:
    with pytest.raises(UnknownComplicationError, match="chuva"):
        plan_matrix(["nenhuma", "chuva"])
