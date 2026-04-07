-- Preenche data_quitacao para parcelas já marcadas como pagas sem data (uma vez).
-- Opcional: ajuste manualmente no Table Editor se a data real for outra.

UPDATE pedido_parcelas
SET data_quitacao = data_pagamento::date
WHERE pago IS TRUE
  AND data_quitacao IS NULL;
