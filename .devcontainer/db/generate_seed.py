# /// script
# requires-python = ">=3.12"
# dependencies = ["faker"]
# ///
"""Write .devcontainer/db/seed.sql to stdout: `uv run .devcontainer/db/generate_seed.py > .devcontainer/db/seed.sql`.

Everything random is seeded, so two runs give identical output. Dates are
emitted as SQL expressions relative to CURRENT_DATE in America/Sao_Paulo, so
the committed seed stays fresh whenever it is applied.
"""

import random
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from faker import Faker

SEED = 20260
CENT = Decimal("0.01")
DEFAULT_CAPACITY = Decimal("15.0")
N_CUSTOMERS = 120
N_ORDERS = 200

ALLERGENS = [
    ("gluten", "Glúten"),
    ("lactose", "Lactose"),
    ("egg", "Ovo"),
    ("peanut", "Amendoim"),
    ("tree_nuts", "Castanhas e nozes"),
    ("soy", "Soja"),
]

C, M = "contains", "may_contain"
# slug, name, description, price/kg, cost/kg, custom, allergen links
PRODUCTS = [
    ("bolo-chocolate", "Bolo de chocolate", "Massa de chocolate com recheio e cobertura de brigadeiro.", "89.90", "32.00", False,
     {"gluten": C, "lactose": C, "egg": C, "soy": M}),
    ("bolo-cenoura", "Bolo de cenoura", "Massa de cenoura com cobertura de chocolate.", "79.90", "27.00", False,
     {"gluten": C, "lactose": C, "egg": C}),
    ("bolo-ninho-morango", "Bolo de leite Ninho com morango", "Massa branca, creme de leite Ninho e morangos frescos.", "99.90", "38.00", False,
     {"gluten": C, "lactose": C, "egg": C}),
    ("bolo-red-velvet", "Bolo red velvet", "Massa aveludada vermelha com recheio de cream cheese.", "109.90", "41.00", False,
     {"gluten": C, "lactose": C, "egg": C}),
    ("bolo-limao", "Bolo de limão", "Massa amanteigada com recheio e cobertura de limão siciliano.", "84.90", "29.00", False,
     {"gluten": C, "lactose": C, "egg": C}),
    ("bolo-coco", "Bolo de coco gelado", "Massa branca molhadinha com creme e coco fresco.", "79.90", "26.00", False,
     {"gluten": C, "lactose": C, "egg": C}),
    ("bolo-prestigio", "Bolo prestígio", "Massa de chocolate com recheio de coco e cobertura de chocolate.", "94.90", "34.00", False,
     {"gluten": C, "lactose": C, "egg": C, "soy": M}),
    ("bolo-doce-de-leite-nozes", "Bolo de doce de leite com nozes", "Massa de baunilha, doce de leite e nozes.", "104.90", "40.00", False,
     {"gluten": C, "lactose": C, "egg": C, "tree_nuts": C, "peanut": M}),
    ("torta-chocolate-sem-farinha", "Torta de chocolate sem farinha", "Torta densa de chocolate meio amargo, feita sem farinha de trigo.", "119.90", "45.00", False,
     {"lactose": C, "egg": C, "gluten": M}),
    ("bolo-brigadeiro-branco", "Bolo de brigadeiro branco", "Massa branca com recheio e cobertura de brigadeiro branco.", "92.90", "33.00", False,
     {"gluten": C, "lactose": C, "egg": C}),
    ("personalizado-tema", "Bolo personalizado com tema", "Bolo de tema infantil ou festa, sabor e decoração combinados com a confeiteira.", "139.90", "55.00", True,
     {"gluten": C, "lactose": C, "egg": C, "peanut": M, "tree_nuts": M, "soy": M}),
    ("personalizado-pasta-americana", "Bolo decorado em pasta americana", "Bolo coberto com pasta americana e topo modelado sob encomenda.", "149.90", "60.00", True,
     {"gluten": C, "lactose": C, "egg": C, "soy": M}),
]

PANS = [("P", "Forma pequena", "1.0", "2.0"), ("M", "Forma média", "2.0", "3.5"), ("G", "Forma grande", "3.5", "6.0")]

# The shop is in Imbiribeira, so it has the lowest fee.
NEIGHBORHOODS = [
    ("Imbiribeira", "8.00"), ("Ipsep", "10.00"), ("Areias", "12.00"), ("Pina", "14.00"),
    ("Boa Viagem", "15.00"), ("Afogados", "16.00"), ("Ibura", "18.00"), ("Jordão", "20.00"),
]

# code, percent, valid_from offset, valid_until offset, max_uses, active
COUPONS = [
    ("AMIGO5", 5, -60, 120, None, True),        # valid
    ("PASCOA10", 10, -120, -60, None, True),    # expired
    ("PRIMEIRA10", 10, -120, 180, 5, True),     # used up (5 non-cancelled orders)
    ("VERAO8", 8, 30, 90, None, True),          # not yet valid
    ("ANTIGO5", 5, -200, 200, None, False),     # inactive
]

HOLIDAYS = [
    (1, 1, "Confraternização Universal"), (4, 21, "Tiradentes"), (5, 1, "Dia do Trabalho"),
    (9, 7, "Independência do Brasil"), (10, 12, "Nossa Senhora Aparecida"), (11, 2, "Finados"),
    (11, 15, "Proclamação da República"), (11, 20, "Consciência Negra"), (12, 25, "Natal"),
]

PHOTO_DESCRIPTIONS = [
    "Bolo de dois andares com flores de pasta americana em tons de rosa.",
    "Foto de um bolo com tema de futebol, gramado verde e bola no topo.",
    "Bolo simples, cobertura lisa branca e morangos inteiros por cima.",
    "Bolo com tema de unicórnio, cores pastel e chifre dourado.",
    "Bolo retangular com o nome da aniversariante escrito em chocolate.",
    "Bolo com tema de super-heróis, máscara e escudo no topo.",
    "Bolo naked cake com frutas vermelhas e flores comestíveis.",
    "Bolo de formatura com capelo de chocolate e o ano em dourado.",
]
NOTES = [
    "Por favor, escrever 'Parabéns, Ana!' no topo.",
    "Sem velas, por favor.",
    "Entregar até as 15h, a festa começa às 16h.",
    "Pouco açúcar na cobertura, se possível.",
    "Tocar a campainha duas vezes ao chegar.",
    "Vela com o número 7.",
    "Embalagem para presente.",
]
CANCEL_REASONS = [
    "Mudança de planos da festa.",
    "Cliente não conseguiu pagar o sinal a tempo.",
    "Data da festa foi alterada.",
    "Cliente encontrou outro fornecedor.",
]


def q(value: str | None) -> str:
    """SQL string literal, or NULL."""
    return "NULL" if value is None else "'" + value.replace("'", "''") + "'"


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def ts(offset: int, minutes: int) -> str:
    """timestamptz expression: day offset from today plus time of day."""
    h, m = divmod(minutes, 60)
    return f"CURRENT_DATE + {offset} + TIME '{h:02d}:{m:02d}'"


def dt(offset: int) -> str:
    return f"CURRENT_DATE + {offset}"


@dataclass
class Order:
    day: int  # delivery date offset from today
    product: int  # 1-based product id
    pan: str
    weight: Decimal
    pickup: bool
    neighborhood: int | None = None
    custom: bool = False
    customer: int = 0
    status: str = ""
    coupon: str | None = None
    created_day: int = 0
    created_min: int = 0
    cancelled_day: int = 0


def pans_containing(weight: Decimal) -> list[str]:
    return [c for c, _, lo, hi in PANS if Decimal(lo) <= weight <= Decimal(hi)]


def split_weight(rng: random.Random, total: Decimal) -> list[Decimal]:
    """Split `total` kg into cake weights (1.0..6.0 kg, 0.5 steps) adding up exactly."""
    parts: list[Decimal] = []
    remaining = total
    while remaining > 0:
        options = [
            Decimal(w) / 2
            for w in range(2, 13)
            if Decimal(w) / 2 <= remaining and (remaining - Decimal(w) / 2 == 0 or remaining - Decimal(w) / 2 >= 1)
        ]
        w = rng.choice(options)
        parts.append(w)
        remaining -= w
    return parts


def main() -> None:
    fake = Faker("pt_BR")
    Faker.seed(SEED)
    rng = random.Random(SEED)
    custom_ids = {i for i, p in enumerate(PRODUCTS, 1) if p[5]}
    regular_ids = [i for i in range(1, len(PRODUCTS) + 1) if i not in custom_ids]

    def draft(day: int, weight: Decimal | None = None, allow_custom: bool = True) -> Order:
        product = rng.choice(regular_ids + (sorted(custom_ids) if allow_custom and rng.random() < 0.15 else []))
        if weight is None:
            pan = rng.choice(["P", "M", "M", "G"])
            lo, hi = next((Decimal(a), Decimal(b)) for c, _, a, b in PANS if c == pan)
            weight = Decimal(rng.randint(int(lo * 2), int(hi * 2))) / 2
        pan = rng.choice(pans_containing(weight))
        pickup = rng.random() < 0.35
        return Order(day, product, pan, weight, pickup,
                     None if pickup else rng.randint(1, len(NEIGHBORHOODS)), product in custom_ids)

    # Capacity fixtures: day +3 and +4 full, day +5 with 2 kg free.
    orders: list[Order] = []
    booked: dict[int, Decimal] = {}
    for day, total in ((3, Decimal("15.0")), (4, Decimal("15.0")), (5, Decimal("13.0"))):
        for w in split_weight(rng, total):
            orders.append(draft(day, w))
        booked[day] = total

    # The rest, spread over -90..+14 without exceeding the default capacity.
    while len(orders) < N_ORDERS:
        day = rng.randint(-90, -1) if rng.random() < 0.7 else rng.choice([0, 1, 2, 6, 7, 8, 9, 10, 11, 12, 13, 14])
        o = draft(day)
        cancelled = day < 0 and rng.random() < 0.12
        if not cancelled and booked.get(day, Decimal(0)) + o.weight > DEFAULT_CAPACITY:
            continue
        o.status = "cancelled" if cancelled else ""
        if not cancelled:
            booked[day] = booked.get(day, Decimal(0)) + o.weight
        orders.append(o)

    orders.sort(key=lambda o: (o.day, o.product, o.weight))  # stable ids; rng order kept otherwise

    for o in orders:
        if o.status != "cancelled":
            o.status = ("delivered" if o.day < 0 else rng.choices(["confirmed", "pending_payment"], [7, 3])[0])
        lead = rng.randint(5, 14) if o.custom else rng.randint(3, 14)
        o.created_day = min(o.day - lead, -1)
        o.created_min = rng.randint(8 * 60, 19 * 60)
        if o.status == "cancelled":
            o.cancelled_day = rng.randint(o.created_day, o.day - 1)

    # Customers: everyone has at least one order, the rest are returning buyers.
    owners = list(range(1, N_CUSTOMERS + 1)) + [rng.randint(1, N_CUSTOMERS) for _ in range(len(orders) - N_CUSTOMERS)]
    rng.shuffle(owners)
    for o, c in zip(orders, owners):
        o.customer = c

    # Coupons. PRIMEIRA10 reaches max_uses exactly on past non-cancelled orders.
    live = [o for o in orders if o.status != "cancelled"]
    for o in rng.sample([o for o in live if o.day < 0], 5):
        o.coupon = "PRIMEIRA10"
    for o in rng.sample([o for o in live if -60 <= o.day <= 14 and o.coupon is None and o.day not in (3, 4, 5)], 12):
        o.coupon = "AMIGO5"
    for o in rng.sample([o for o in live if -90 <= o.day <= -60 and o.coupon is None], 6):
        o.coupon = "PASCOA10"
    percent = {c[0]: c[1] for c in COUPONS}

    # Customer rows.
    first_order = {}
    for o in orders:
        first_order[o.customer] = min(first_order.get(o.customer, 0), o.created_day)
    phones: set[str] = set()
    customers = []
    for cid in range(1, N_CUSTOMERS + 1):
        while True:
            phone = "+55819" + "".join(rng.choice("0123456789") for _ in range(8))
            if phone not in phones:
                phones.add(phone)
                break
        name = f"{fake.first_name()} {fake.last_name()}"
        customers.append((name, phone, first_order[cid] - rng.randint(0, 30)))

    out: list[str] = []
    w = out.append
    w("-- Generated by .devcontainer/db/generate_seed.py. Do not edit by hand; regenerate with:")
    w("--   uv run .devcontainer/db/generate_seed.py > .devcontainer/db/seed.sql")
    w("-- Apply after .devcontainer/db/schema.sql, on empty tables. All dates are relative to the")
    w("-- current date in America/Sao_Paulo (the server runs in UTC).")
    w("SET TIME ZONE 'America/Sao_Paulo';")
    w("BEGIN;")

    w("\nINSERT INTO allergens (code, name) VALUES")
    w(",\n".join(f"  ({q(c)}, {q(n)})" for c, n in ALLERGENS) + ";")

    w("\nINSERT INTO products (slug, name, description, price_per_kg, cost_per_kg, is_custom) VALUES")
    w(",\n".join(f"  ({q(s)}, {q(n)}, {q(d)}, {p}, {c}, {str(cu).lower()})" for s, n, d, p, c, cu, _ in PRODUCTS) + ";")

    w("\nINSERT INTO product_allergens (product_id, allergen_code, kind) VALUES")
    w(",\n".join(f"  ({i}, {q(a)}, {q(k)})" for i, p in enumerate(PRODUCTS, 1) for a, k in p[6].items()) + ";")

    w("\nINSERT INTO pan_sizes (code, name, min_kg, max_kg) VALUES")
    w(",\n".join(f"  ({q(c)}, {q(n)}, {lo}, {hi})" for c, n, lo, hi in PANS) + ";")

    w("\nINSERT INTO neighborhoods (name, delivery_fee) VALUES")
    w(",\n".join(f"  ({q(n)}, {f})" for n, f in NEIGHBORHOODS) + ";")

    w("\nINSERT INTO coupons (code, percent_off, valid_from, valid_until, max_uses, active) VALUES")
    w(",\n".join(
        f"  ({q(c)}, {p}, {dt(a)}, {dt(b)}, {'NULL' if m is None else m}, {str(act).lower()})"
        for c, p, a, b, m, act in COUPONS) + ";")

    w("\n-- Fixed-day holidays for this year and the next (closed), plus a busy Dec 24.")
    w("INSERT INTO capacity_overrides (date, capacity_kg, reason) VALUES")
    rows = []
    for k in (0, 1):
        for m, d, reason in HOLIDAYS:
            rows.append(f"  (make_date(extract(year FROM CURRENT_DATE)::int + {k}, {m}, {d}), 0, {q(reason)})")
        rows.append(f"  (make_date(extract(year FROM CURRENT_DATE)::int + {k}, 12, 24), 25, 'Véspera de Natal')")
    w(",\n".join(rows) + ";")

    w("\nINSERT INTO customers (name, phone, created_at) VALUES")
    w(",\n".join(f"  ({q(n)}, {q(p)}, {ts(d, 9 * 60)})" for n, p, d in customers) + ";")

    order_rows, msg_rows = [], []
    for oid, o in enumerate(orders, 1):
        price = Decimal(PRODUCTS[o.product - 1][3])
        fee = Decimal(0) if o.pickup else Decimal(NEIGHBORHOODS[o.neighborhood - 1][1])
        subtotal = price * o.weight
        assert subtotal == subtotal.quantize(CENT), subtotal
        discount = (subtotal * percent[o.coupon] / 100).quantize(CENT, rounding=ROUND_HALF_UP) if o.coupon else Decimal(0)
        total = subtotal + fee - discount
        deposit = (total / 2).quantize(CENT, rounding=ROUND_HALF_UP)
        address = None if o.pickup else f"{fake.street_name()}, {rng.randint(1, 999)} - {NEIGHBORHOODS[o.neighborhood - 1][0]}, Recife - PE"
        photo = rng.choice(PHOTO_DESCRIPTIONS) if rng.random() < 0.5 else None
        notes = rng.choice(NOTES) if rng.random() < 0.3 else None
        cancelled = o.status == "cancelled"
        refund = money(deposit if o.day - o.cancelled_day >= 3 else Decimal(0)) if cancelled else "NULL"
        order_rows.append(
            f"  ({o.customer}, {o.product}, {q(o.pan)}, {'NULL' if o.neighborhood is None else o.neighborhood}, "
            f"{q(o.coupon)}, {dt(o.day)}, {q('pickup' if o.pickup else 'delivery')}, {q(address)}, {q(photo)}, {q(notes)}, "
            f"{q(o.status)}, {o.weight}, {money(price)}, {money(subtotal)}, {money(fee)}, {money(discount)}, "
            f"{money(total)}, {money(deposit)}, {q(f'https://pagamento.fornada.example/pedido/{oid}')}, "
            f"{ts(o.created_day, o.created_min)}, "
            f"{ts(o.cancelled_day, 21 * 60) if cancelled else 'NULL'}, {refund}, "
            f"{q(rng.choice(CANCEL_REASONS)) if cancelled else 'NULL'})"
        )
        if not cancelled:
            first = customers[o.customer - 1][0].split()[0]
            body = (f"Olá, {first}! Recebemos seu pedido #{oid}: {PRODUCTS[o.product - 1][1]}, {o.weight} kg. "
                    f"Total R$ {money(total)}, sinal de R$ {money(deposit)}. Pagamento: https://pagamento.fornada.example/pedido/{oid}")
            msg_rows.append(f"  ({q(customers[o.customer - 1][1])}, {q(body)}, {oid}, {ts(o.created_day, o.created_min + 2)})")

    w("\nINSERT INTO orders (customer_id, product_id, pan_size_code, neighborhood_id, coupon_code, delivery_date,"
      " fulfillment, address, reference_photo_description, notes, status, weight_kg, price_per_kg, subtotal,"
      " delivery_fee, discount, total, deposit, payment_link, created_at, cancelled_at, refund_amount, cancel_reason) VALUES")
    w(",\n".join(order_rows) + ";")

    w("\nINSERT INTO sent_messages (to_phone, body, order_id, created_at) VALUES")
    w(",\n".join(msg_rows) + ";")

    w("\nCOMMIT;")
    print("\n".join(out))


if __name__ == "__main__":
    main()
