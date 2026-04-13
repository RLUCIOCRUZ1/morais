"""Sessão de login (usuários em app_usuarios)."""

from __future__ import annotations

import streamlit as st

from services import usuarios_app as ua


def init_auth_session() -> None:
    if "auth_logged_in" not in st.session_state:
        st.session_state.auth_logged_in = False
    if "auth_user_id" not in st.session_state:
        st.session_state.auth_user_id = None
    if "auth_email" not in st.session_state:
        st.session_state.auth_email = None
    if "auth_nome" not in st.session_state:
        st.session_state.auth_nome = None
    if "auth_perfil" not in st.session_state:
        st.session_state.auth_perfil = None


def is_logged_in() -> bool:
    init_auth_session()
    return bool(st.session_state.auth_logged_in)


def is_admin() -> bool:
    init_auth_session()
    return st.session_state.auth_perfil == "admin"


def get_perfil() -> str | None:
    init_auth_session()
    return st.session_state.auth_perfil


def login_por_email_senha(email: str, senha: str) -> tuple[bool, str | None]:
    """Retorna (ok, mensagem_erro)."""
    init_auth_session()
    row = ua.buscar_por_email(email)
    if not row:
        return False, "E-mail ou senha incorretos."
    if not row.get("ativo", True):
        return False, "Usuário inativo. Peça ao administrador."
    if not row.get("senha_hash"):
        return False, "Conta sem senha cadastrada. Peça ao administrador para redefinir o acesso."
    if not ua.verificar_senha(senha, row.get("senha_hash") or ""):
        return False, "E-mail ou senha incorretos."
    st.session_state.auth_logged_in = True
    st.session_state.auth_user_id = row["id"]
    st.session_state.auth_email = row["email"]
    st.session_state.auth_nome = row.get("nome") or ""
    st.session_state.auth_perfil = row["perfil"]
    return True, None


def logout() -> None:
    init_auth_session()
    st.session_state.auth_logged_in = False
    st.session_state.auth_user_id = None
    st.session_state.auth_email = None
    st.session_state.auth_nome = None
    st.session_state.auth_perfil = None


def require_login() -> None:
    init_auth_session()
    if not st.session_state.auth_logged_in:
        st.switch_page("app.py")


def require_admin() -> None:
    require_login()
    if st.session_state.auth_perfil != "admin":
        st.switch_page("app.py")


def show_auth_controls_sidebar() -> None:
    """Chame dentro de `with st.sidebar:` (após logo)."""
    init_auth_session()
    if not st.session_state.auth_logged_in:
        return
    perfil_label = "Administrativo" if st.session_state.auth_perfil == "admin" else "Cadastro"
    st.caption(f"**{st.session_state.auth_nome or st.session_state.auth_email}** · {perfil_label}")
    if st.button("Sair", key="auth_logout_sidebar", width="stretch"):
        logout()
        st.switch_page("app.py")
