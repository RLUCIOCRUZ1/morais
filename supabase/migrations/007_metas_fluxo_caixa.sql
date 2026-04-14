CREATE TABLE IF NOT EXISTS metas_fluxo_caixa (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ano         integer NOT NULL,
    mes         integer NOT NULL CHECK (mes BETWEEN 1 AND 12),
    valor       numeric(14, 2) NOT NULL DEFAULT 0,
    created_at  timestamptz DEFAULT now(),
    UNIQUE (ano, mes)
);
