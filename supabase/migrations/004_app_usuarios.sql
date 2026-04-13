-- Usuários do app Streamlit (login + perfis administrativo / cadastro).
-- Execute no SQL Editor do Supabase (uma vez).

CREATE TABLE IF NOT EXISTS app_usuarios (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    nome text NOT NULL,
    email text NOT NULL UNIQUE,
    senha_hash text NOT NULL,
    perfil text NOT NULL CHECK (perfil IN ('admin', 'cadastro')),
    ativo boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_app_usuarios_email_lower ON app_usuarios (lower(email));

COMMENT ON TABLE app_usuarios IS 'Login interno Morais: admin = todas as telas; cadastro = sem financeiro.';

-- Sem RLS: o acesso fica no backend (Streamlit + SUPABASE_KEY). Para endurecer depois,
-- habilite RLS e use a service role só nas operações desta tabela.
