-- Fornada dev schema. Drops and recreates only the app tables (never the
-- LangGraph checkpointer's). Integrity constraints only: business rules live
-- in the tools. See openspec/changes/add-dev-database-seed/design.md.
BEGIN;

DROP TABLE IF EXISTS escalations, sent_messages, orders, customers, coupons,
    capacity_overrides, neighborhoods, pan_sizes, product_allergens, allergens,
    products CASCADE;

CREATE TABLE products (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug          text NOT NULL UNIQUE,
    name          text NOT NULL,
    description   text NOT NULL,
    price_per_kg  numeric(10,2) NOT NULL CHECK (price_per_kg >= 0),
    cost_per_kg   numeric(10,2) NOT NULL CHECK (cost_per_kg >= 0),
    is_custom     boolean NOT NULL DEFAULT false,
    active        boolean NOT NULL DEFAULT true
);

CREATE TABLE allergens (
    code text PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE product_allergens (
    product_id    bigint NOT NULL REFERENCES products (id),
    allergen_code text NOT NULL REFERENCES allergens (code),
    kind          text NOT NULL CHECK (kind IN ('contains', 'may_contain')),
    PRIMARY KEY (product_id, allergen_code)
);

CREATE TABLE pan_sizes (
    code   text PRIMARY KEY,
    name   text NOT NULL,
    min_kg numeric(4,1) NOT NULL CHECK (min_kg > 0),
    max_kg numeric(4,1) NOT NULL,
    CHECK (min_kg < max_kg)
);

CREATE TABLE neighborhoods (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         text NOT NULL UNIQUE,
    delivery_fee numeric(10,2) NOT NULL CHECK (delivery_fee >= 0),
    active       boolean NOT NULL DEFAULT true
);

CREATE TABLE capacity_overrides (
    date        date PRIMARY KEY,
    capacity_kg numeric(5,1) NOT NULL CHECK (capacity_kg >= 0),
    reason      text NOT NULL
);

-- No bound on percent_off on purpose: apply_coupon owns the 10% rule.
-- Usage is derived by counting orders, there is no counter.
CREATE TABLE coupons (
    code        text PRIMARY KEY,
    percent_off integer NOT NULL,
    valid_from  date NOT NULL,
    valid_until date NOT NULL,
    max_uses    integer,
    active      boolean NOT NULL DEFAULT true
);

CREATE TABLE customers (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name       text NOT NULL,
    phone      text NOT NULL UNIQUE CHECK (phone ~ '^\+55[0-9]{10,11}$'),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- One cake per order. Amounts are snapshots; nothing checks that they add up.
CREATE TABLE orders (
    id                          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id                 bigint NOT NULL REFERENCES customers (id),
    product_id                  bigint NOT NULL REFERENCES products (id),
    pan_size_code               text NOT NULL REFERENCES pan_sizes (code),
    neighborhood_id             bigint REFERENCES neighborhoods (id),
    coupon_code                 text REFERENCES coupons (code),
    delivery_date               date NOT NULL,
    fulfillment                 text NOT NULL CHECK (fulfillment IN ('pickup', 'delivery')),
    address                     text,
    reference_photo_description text,
    notes                       text,
    status                      text NOT NULL
        CHECK (status IN ('pending_payment', 'confirmed', 'delivered', 'cancelled')),
    weight_kg                   numeric(4,1) NOT NULL
        CHECK (weight_kg > 0 AND mod(weight_kg, 0.5) = 0),
    price_per_kg                numeric(10,2) NOT NULL CHECK (price_per_kg >= 0),
    subtotal                    numeric(10,2) NOT NULL CHECK (subtotal >= 0),
    delivery_fee                numeric(10,2) NOT NULL CHECK (delivery_fee >= 0),
    discount                    numeric(10,2) NOT NULL CHECK (discount >= 0),
    total                       numeric(10,2) NOT NULL CHECK (total >= 0),
    deposit                     numeric(10,2) NOT NULL CHECK (deposit >= 0),
    payment_link                text,
    created_at                  timestamptz NOT NULL DEFAULT now(),
    cancelled_at                timestamptz,
    refund_amount               numeric(10,2) CHECK (refund_amount >= 0),
    cancel_reason               text,
    CHECK ((fulfillment = 'delivery' AND neighborhood_id IS NOT NULL AND address IS NOT NULL)
        OR (fulfillment = 'pickup' AND neighborhood_id IS NULL AND address IS NULL)),
    CHECK ((status = 'cancelled') = (cancelled_at IS NOT NULL)
       AND (status = 'cancelled') = (refund_amount IS NOT NULL))
);
CREATE INDEX orders_delivery_date_idx ON orders (delivery_date);
CREATE INDEX orders_customer_id_idx ON orders (customer_id);

-- No FK to customers, so a message to an arbitrary number is representable.
CREATE TABLE sent_messages (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    to_phone   text NOT NULL,
    body       text NOT NULL,
    order_id   bigint REFERENCES orders (id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE escalations (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    thread_id  text NOT NULL,
    phone      text,
    reason     text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

COMMIT;
