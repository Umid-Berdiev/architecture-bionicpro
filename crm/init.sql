-- Emulated CRM database (in production: Bitrix24 on Oracle, see Task2/README.md).
-- Customers are linked to the identity provider by the stable subject id (Keycloak user id).

CREATE TABLE customers (
    id            SERIAL PRIMARY KEY,
    idp_user_id   UUID        NOT NULL UNIQUE,
    username      TEXT        NOT NULL UNIQUE,
    full_name     TEXT        NOT NULL,
    email         TEXT        NOT NULL,
    country       CHAR(2)     NOT NULL DEFAULT 'RU',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE prostheses (
    id               SERIAL PRIMARY KEY,
    customer_id      INTEGER     NOT NULL REFERENCES customers(id),
    serial_number    TEXT        NOT NULL UNIQUE,
    model            TEXT        NOT NULL,
    side             TEXT        NOT NULL CHECK (side IN ('left', 'right')),
    firmware_version TEXT        NOT NULL,
    delivered_at     DATE        NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO customers (idp_user_id, username, full_name, email, country) VALUES
    ('00000000-0000-4000-8000-000000000301', 'prothetic1', 'Иванов Пётр Сергеевич',   'prothetic1@example.com', 'RU'),
    ('00000000-0000-4000-8000-000000000302', 'prothetic2', 'Смирнова Анна Викторовна', 'prothetic2@example.com', 'RU'),
    ('00000000-0000-4000-8000-000000000303', 'prothetic3', 'Кузнецов Олег Дмитриевич', 'prothetic3@example.com', 'RU'),
    ('00000000-0000-4000-8000-000000000101', 'user1',      'Петрова Мария Ильинична',  'user1@example.com',      'RU'),
    ('00000000-0000-4000-8000-000000000102', 'user2',      'Сидоров Иван Андреевич',   'user2@example.com',      'RU');

INSERT INTO prostheses (customer_id, serial_number, model, side, firmware_version, delivered_at) VALUES
    ((SELECT id FROM customers WHERE username = 'prothetic1'), 'BP-ARM-2024-0001', 'BionicArm Pro 2', 'right', '2.4.1', '2024-03-12'),
    ((SELECT id FROM customers WHERE username = 'prothetic2'), 'BP-ARM-2024-0002', 'BionicArm Pro 2', 'left',  '2.4.1', '2024-05-20'),
    ((SELECT id FROM customers WHERE username = 'prothetic2'), 'BP-HND-2025-0003', 'BionicHand Lite', 'right', '1.9.0', '2025-01-15'),
    ((SELECT id FROM customers WHERE username = 'prothetic3'), 'BP-ARM-2025-0004', 'BionicArm Pro 3', 'right', '3.0.2', '2025-06-02');
