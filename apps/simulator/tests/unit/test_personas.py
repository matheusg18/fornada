import re

from fornada_api.agents.attendant.metrics import PERSONAS as API_PERSONAS

from fornada_simulator.personas import PERSONAS

# The persona must read as a customer: no word that reveals what is under test.
FORBIDDEN = re.compile(
    r"\b(ferramentas?|tools?|prompts?|evals?|testes?|simulador|simulação)\b", re.I
)


def test_five_distinct_personas() -> None:
    assert len(PERSONAS) == 5
    assert len({persona.id for persona in PERSONAS}) == 5


def test_each_persona_has_at_least_four_distinct_goals() -> None:
    for persona in PERSONAS:
        assert len(persona.goals) >= 4, persona.id
        assert len(set(persona.goals)) == len(persona.goals), persona.id


def test_persona_text_does_not_reveal_the_test() -> None:
    for persona in PERSONAS:
        for text in (persona.description, *persona.goals):
            assert not FORBIDDEN.search(text), (persona.id, text)


def test_persona_ids_match_the_apis_allowlist() -> None:
    # The API records any other id as `other`: adding a persona here without
    # adding it there would hide it on every metric.
    assert {persona.id for persona in PERSONAS} == API_PERSONAS
