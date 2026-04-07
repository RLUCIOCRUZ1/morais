-- Data em que a parcela foi marcada como paga no financeiro (baixa).
-- Execute no SQL Editor do Supabase (após 001_add_status_columns.sql).

ALTER TABLE pedido_parcelas
  ADD COLUMN IF NOT EXISTS data_quitacao date;

COMMENT ON COLUMN pedido_parcelas.data_quitacao IS 'Data do registro de pagamento (marcação como pago)';
