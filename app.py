import streamlit as st

from services.auth import (
    init_auth_session,
    is_admin,
    is_logged_in,
    login_por_email_senha,
)
from services.branding import show_home_logo_centered, show_sidebar_branding
from services import usuarios_app as ua

st.set_page_config(
    page_title="Controle de OTB e Fluxo de Caixa",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_auth_session()


def _contar_usuarios_ou_erro() -> int | None:
    try:
        return ua.contar_usuarios()
    except Exception:
        return None


n_usuarios = _contar_usuarios_ou_erro()

if n_usuarios is None:
    show_sidebar_branding()
    st.error(
        "Não foi possível ler a tabela **app_usuarios**. "
        "Execute a migração `supabase/migrations/004_app_usuarios.sql` no SQL Editor do Supabase."
    )
    st.stop()

# --- Primeiro acesso: criar administrador (só se a tabela estiver vazia) ---
if n_usuarios == 0:
    show_sidebar_branding()
    st.warning("Primeiro acesso: crie o usuário **administrativo** inicial.")
    with st.form("bootstrap_admin"):
        b_nome = st.text_input("Nome")
        b_email = st.text_input("E-mail (será o login)")
        b_senha = st.text_input("Senha", type="password")
        b_senha2 = st.text_input("Repita a senha", type="password")
        if st.form_submit_button("Criar administrador", type="primary", width="stretch"):
            if not b_nome.strip():
                st.error("Informe o nome.")
            elif b_senha != b_senha2:
                st.error("As senhas não coincidem.")
            else:
                try:
                    ua.criar_usuario(b_nome, b_email, b_senha, "admin")
                    st.success("Administrador criado. Faça login abaixo na próxima execução.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro: {e}")
    st.stop()

# --- Login ---
if not is_logged_in():
    show_sidebar_branding()
    st.markdown("### Entrar")
    with st.form("login_form"):
        lg_email = st.text_input("E-mail")
        lg_senha = st.text_input("Senha", type="password")
        ok = st.form_submit_button("Entrar", type="primary", width="stretch")
        if ok:
            success, err = login_por_email_senha(lg_email, lg_senha)
            if success:
                st.rerun()
            else:
                st.error(err or "Falha no login.")
    st.stop()

# --- Home autenticada ---
show_sidebar_branding()

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2rem;
        padding-bottom: 3rem;
        max-width: min(1400px, 100%);
    }
    .home-hero {
        text-align: center;
        padding: 0 0 1.75rem;
    }
    .home-hero h1 {
        font-size: clamp(1.75rem, 4vw, 2.35rem);
        font-weight: 700;
        margin-bottom: 0;
        letter-spacing: -0.02em;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] h3 {
        font-size: 1.12rem !important;
        line-height: 1.35 !important;
        margin-bottom: 0.5rem !important;
        white-space: nowrap;
        overflow: visible;
    }
    @media (min-width: 900px) {
        div[data-testid="stVerticalBlockBorderWrapper"] h3 {
            font-size: 1.22rem !important;
        }
    }
    @media (max-width: 640px) {
        div[data-testid="stVerticalBlockBorderWrapper"] h3 {
            white-space: normal;
        }
    }
    .home-footnote {
        text-align: center;
        margin-top: 2.5rem;
        font-size: 0.9rem;
        color: rgba(49, 51, 63, 0.55);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

show_home_logo_centered()

st.markdown(
    """
    <div class="home-hero">
        <h1>Controle de OTB e Fluxo de Caixa</h1>
    </div>
    """,
    unsafe_allow_html=True,
)

if is_admin():
    col1, col2, col3 = st.columns(3, gap="large")
else:
    col1, col2 = st.columns(2, gap="large")
    col3 = None

with col1:
    with st.container(border=True):
        st.markdown("### 📝 Cadastro")
        st.caption(
            "Pedidos, parcelas e lançamentos. Mantenha a base atualizada para os dashboards."
        )
        if st.button(
            "Abrir Cadastro",
            key="go_cadastro",
            width="stretch",
            type="primary",
        ):
            st.switch_page("pages/Cadastro.py")

with col2:
    with st.container(border=True):
        st.markdown("### 📦 Dashboard OTB")
        st.caption(
            "Planejamento de compras: quantidades, valores por mês, marca e grupo."
        )
        if st.button(
            "Abrir OTB",
            key="go_otb",
            width="stretch",
        ):
            st.switch_page("pages/Dashboard_OTB.py")

if col3 is not None:
    with col3:
        with st.container(border=True):
            st.markdown("### 💰 Dashboard Financeiro")
            st.caption(
                "Fluxo de caixa: parcelas pagas, fornecedores, marcas e indicadores."
            )
            if st.button(
                "Abrir Financeiro",
                key="go_fin",
                width="stretch",
            ):
                st.switch_page("pages/Dashboard_Financeiro.py")

if is_admin():
    st.divider()
    st.markdown("#### Administração")
    if st.button(
        "👤 Gerenciar usuários e perfis (alçadas)",
        key="go_admin_users",
        width="stretch",
        help="Criar logins e definir Administrativo ou Cadastro.",
    ):
        st.switch_page("pages/Admin_usuarios.py")

st.markdown(
    """
    <p class="home-footnote">
        Use o menu lateral para navegar. Perfil <strong>Cadastro</strong> não vê o financeiro.
    </p>
    """,
    unsafe_allow_html=True,
)
