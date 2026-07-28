-- Persiste os prazos (dias após entrega) no pedido para recalcular
-- vencimentos das duplicatas ao confirmar o recebimento no OTB.
-- Execute no SQL Editor do Supabase (uma vez), ou via CLI de migrações.

ALTER TABLE pedidos
  ADD COLUMN IF NOT EXISTS prazos_dias jsonb;

COMMENT ON COLUMN pedidos.prazos_dias IS
  'Prazos em dias corridos após a entrega (data_chegada prevista / data_recebimento real); '
  'cada posição do array = uma parcela. Null = modo periodicidade (não recalcula na entrega).';
