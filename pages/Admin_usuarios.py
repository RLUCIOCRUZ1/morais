"""Gestão de usuários (somente administrativo). Página oculta do menu lateral."""

import streamlit as st
import pandas as pd

from services.auth import init_auth_session, require_admin
from services.branding import show_sidebar_branding
from services import usuarios_app as ua

st.set_page_config(page_title="Usuários", layout="wide", page_icon="👤")

require_admin()

show_sidebar_branding()

st.title("👤 Usuários e perfis")
st.caption(
    "Crie logins com **senha no ato do cadastro**, defina **Administrativo** (acesso total) ou **Cadastro** "
    "(cadastro + OTB, sem financeiro)."
)

init_auth_session()
meu_id = st.session_state.auth_user_id

tab_lista, tab_novo = st.tabs(["Lista de usuários", "Novo usuário"])

with tab_novo:
    with st.form("form_novo_usuario", clear_on_submit=True):
        n_nome = st.text_input("Nome completo")
        n_email = st.text_input("E-mail (login)")
        n_perfil = st.selectbox(
            "Perfil (alçada)",
            options=["admin", "cadastro"],
            format_func=lambda x: "Administrativo — todas as telas"
            if x == "admin"
            else "Cadastro — sem financeiro",
        )
        n_senha = st.text_input("Senha de acesso", type="password", help="Mínimo 6 caracteres.")
        n_senha2 = st.text_input("Repita a senha", type="password")
        sub = st.form_submit_button("Criar usuário", type="primary", width="stretch")
        if sub:
            if n_senha != n_senha2:
                st.error("As senhas não coincidem.")
            else:
                try:
                    created = ua.criar_usuario(n_nome, n_email, n_senha, n_perfil)
                    st.success(f"Usuário criado: **{created.get('email', '')}**.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Não foi possível criar: {e}")

with tab_lista:
    try:
        rows = ua.listar_usuarios_resumo()
    except Exception as e:
        st.error(f"Erro ao listar usuários: {e}")
        st.stop()

    if not rows:
        st.info("Nenhum usuário cadastrado.")
    else:
        df = pd.DataFrame(rows)
        if "senha_hash" in df.columns:
            df = df.drop(columns=["senha_hash"], errors="ignore")
        st.dataframe(df, width="stretch", hide_index=True)

        st.subheader("Alterar perfil, status ou senha")
        op = {f"{r['nome']} <{r['email']}>": r["id"] for r in rows}
        sel_label = st.selectbox("Usuário", list(op.keys()))
        uid = op[sel_label]
        alvo = next(r for r in rows if r["id"] == uid)

        c1, c2 = st.columns(2)
        novo_perfil = c1.selectbox(
            "Perfil",
            options=["admin", "cadastro"],
            index=0 if alvo.get("perfil") == "admin" else 1,
            format_func=lambda x: "Administrativo"
            if x == "admin"
            else "Cadastro (sem financeiro)",
            key="adm_edit_perfil",
        )
        novo_ativo = c2.checkbox("Usuário ativo", value=bool(alvo.get("ativo", True)), key="adm_edit_ativo")

        nova_senha = st.text_input(
            "Nova senha (deixe em branco para não alterar)",
            type="password",
            key="adm_nova_senha",
        )

        if st.button("Salvar alterações", type="primary", key="adm_salvar_user"):
            bloqueio = None
            if uid == meu_id and novo_perfil != "admin":
                bloqueio = "Você não pode remover o próprio perfil administrativo."
            elif uid == meu_id and not novo_ativo:
                bloqueio = "Você não pode desativar a si mesmo."
            elif (novo_perfil != "admin" or not novo_ativo) and alvo.get("perfil") == "admin" and alvo.get(
                "ativo", True
            ):
                if ua.contar_admins_ativos() <= 1:
                    bloqueio = "Deve existir pelo menos um administrativo ativo."
            if bloqueio:
                st.error(bloqueio)
            else:
                try:
                    ua.atualizar_usuario(
                        uid,
                        perfil=novo_perfil,
                        ativo=novo_ativo,
                        nova_senha_plana=nova_senha.strip() if nova_senha.strip() else None,
                    )
                    st.success("Alterações salvas.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao salvar: {e}")
