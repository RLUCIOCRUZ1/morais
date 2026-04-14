ALTER TABLE pedido_itens
ADD COLUMN IF NOT EXISTS descricao text DEFAULT '';
