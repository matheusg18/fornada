"""The persona x intent x complication matrix for phase 3's error analysis.

A cell is one persona, one intent and one complication. Its goal is the
intent's text followed by the complication's; the persona's description, which
sets tone and writing style, is unchanged. The cheater's legacy goals are
attacks and stay out of the matrix.

Texts are Brazilian Portuguese instructions to the customer's model, under the
same rule as the personas: no word that reveals tools, prompts or a test.
Intents use generic slots ("uns 2 kg", "para a semana que vem") that some
complications override explicitly ("Mas a data é outra: ...").

Two complications rely on facts outside the simulator:

- `data_lotada` asks for day +3, which the dev seed fills (reset the database
  before a run, see `.devcontainer/db/README.md`);
- `ferramenta_fora` only asks for a dated order: the outage comes from the API
  running in chaos mode with `CHAOS__CAPACITY_FAILURE_RATE=1`, which is why its
  cells run apart (see `plan_matrix`).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from fornada_simulator.personas import PERSONAS, Persona


@dataclass(frozen=True)
class Intent:
    id: str
    text: str


@dataclass(frozen=True)
class Complication:
    id: str
    # Empty for the control: it adds nothing to the intent.
    text: str


INTENTS: tuple[Intent, ...] = (
    Intent(
        id="retirada",
        text=(
            "Você quer encomendar um bolo de cenoura de uns 2 kg para a semana que vem "
            "e vai retirar na loja."
        ),
    ),
    Intent(
        id="entrega",
        text=(
            "Você quer encomendar um bolo de chocolate de uns 2 kg para a semana que "
            "vem, com entrega no seu endereço, no bairro Boa Viagem."
        ),
    ),
    Intent(
        id="orcamento",
        text=(
            "Você só quer saber quanto fica um bolo de limão de uns 2 kg para a semana "
            "que vem, com entrega em Boa Viagem. Não quer fechar o pedido agora: "
            "quando souber o valor, agradeça e diga que vai pensar."
        ),
    ),
    Intent(
        id="duvida_cardapio",
        text=(
            "Antes de escolher, você quer saber quais sabores a confeitaria tem e o que "
            "cada um leva (ingredientes e alergênicos). Depois escolha um e encomende "
            "uns 2 kg para a semana que vem, retirando na loja."
        ),
    ),
    Intent(
        id="pos_pedido",
        text=(
            "Você quer encomendar um bolo prestígio de uns 2 kg para a semana que vem, "
            "retirando na loja. Depois que o pedido for confirmado, pergunte como está "
            "o seu pedido e, em seguida, desista e peça para cancelar."
        ),
    ),
)

NO_COMPLICATION = "nenhuma"
OUTAGE = "ferramenta_fora"

COMPLICATIONS: tuple[Complication, ...] = (
    Complication(id=NO_COMPLICATION, text=""),
    Complication(
        id="data_lotada",
        text=(
            "Mas a data é outra: você precisa do bolo para daqui a 3 dias. Se disserem "
            "que não dá, aceite outra data próxima."
        ),
    ),
    Complication(
        id="troca_sabor",
        text=(
            "Depois de receber o valor, mude de ideia sobre o sabor, escolha outro do "
            "cardápio e pergunte quanto fica agora."
        ),
    ),
    Complication(
        id=OUTAGE,
        text=(
            "Mas a data é outra: você precisa do bolo para daqui a 6 dias, e quer que a "
            "atendente confirme que essa data está garantida."
        ),
    ),
    Complication(
        id="tamanho_ambiguo",
        text=(
            "Mas você não sabe quantos quilos quer: não fale em quilos, diga só que quer "
            "'um bolo médio, para umas 40 pessoas' e deixe a atendente sugerir o tamanho."
        ),
    ),
)

COMPLICATION_IDS = frozenset(complication.id for complication in COMPLICATIONS)


@dataclass(frozen=True)
class Cell:
    persona: Persona
    intent: Intent
    complication: Complication

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.persona.id, self.intent.id, self.complication.id)

    @property
    def goal(self) -> str:
        if not self.complication.text:
            return self.intent.text
        return f"{self.intent.text} {self.complication.text}"


class UnknownComplicationError(ValueError):
    """A complication id that is not in the catalog."""


def plan_matrix(complications: Sequence[str] | None = None) -> list[Cell]:
    """Every persona x intent x complication cell once, personas interleaved.

    Without a list, every complication but `ferramenta_fora`: its cells need an
    API in chaos mode, so they run only when named, never next to cells that
    need a working capacity check.
    """
    if complications is None:
        selected = [c for c in COMPLICATIONS if c.id != OUTAGE]
    else:
        unknown = sorted(set(complications) - COMPLICATION_IDS)
        if unknown:
            raise UnknownComplicationError(f"unknown complication: {', '.join(unknown)}")
        selected = [c for c in COMPLICATIONS if c.id in complications]
    # Every persona once before any persona again, so a cut batch stays balanced.
    return [
        Cell(persona, intent, complication)
        for intent in INTENTS
        for complication in selected
        for persona in PERSONAS
    ]
