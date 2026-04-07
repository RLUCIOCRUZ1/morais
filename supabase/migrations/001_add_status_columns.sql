-- Execute no SQL Editor do Supabase (uma vez).
-- Parcelas: controle de pagamento no financeiro.
ALTER TABLE pedido_parcelas
  ADD COLUMN IF NOT EXISTS pago boolean NOT NULL DEFAULT false;

-- Pedidos: controle de recebimento no OTB.
ALTER TABLE pedidos
  ADD COLUMN IF NOT EXISTS recebido boolean NOT NULL DEFAULT false;

ALTER TABLE pedidos
  ADD COLUMN IF NOT EXISTS data_recebimento date;

COMMENT ON COLUMN pedido_parcelas.pago IS 'Parcela quitada (baixa no financeiro)';
COMMENT ON COLUMN pedidos.recebido IS 'Mercadoria recebida';
COMMENT ON COLUMN pedidos.data_recebimento IS 'Data do recebimento (opcional)';
