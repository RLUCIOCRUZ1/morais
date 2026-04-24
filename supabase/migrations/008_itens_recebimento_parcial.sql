-- Recebimento parcial: cada item (referência) do pedido pode ser recebido individualmente.
-- Execute no SQL Editor do Supabase (uma vez).

ALTER TABLE pedido_itens
ADD COLUMN IF NOT EXISTS recebido boolean NOT NULL DEFAULT false;

ALTER TABLE pedido_itens
ADD COLUMN IF NOT EXISTS data_recebimento date;
