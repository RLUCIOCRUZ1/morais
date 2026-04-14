"""Logomarca Morais — uso na sidebar e na home."""

from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = _ROOT / "assets" / "logo_morais.png"

# O Streamlit desenha o menu de páginas antes do conteúdo de st.sidebar.
# Este CSS reordena: logo (conteúdo customizado) acima do menu.
_SIDEBAR_LOGO_FIRST_CSS = """
<style>
    /* Coluna principal da sidebar em flex, sem folga entre logo e menu */
    section[data-testid="stSidebar"] > div {
        display: flex !important;
        flex-direction: column !important;
        gap: 0 !important;
    }
    /* Menu multipage (app, Cadastro, ...) fica logo abaixo do logo */
    [data-testid="stSidebarNav"] {
        order: 2 !important;
        margin-top: 0 !important;
        padding-top: 0.35rem !important;
    }
    /* Tudo que vem depois do menu no DOM = conteúdo de st.sidebar (logo) — sobe */
    [data-testid="stSidebarNav"] ~ * {
        order: 1 !important;
    }
    /* Menos espaço sob a imagem / linha do logo */
    [data-testid="stSidebarNav"] ~ * [data-testid="stImage"] {
        margin-bottom: 0 !important;
    }
    [data-testid="stSidebarNav"] ~ * hr {
        margin-top: 0.2rem !important;
        margin-bottom: 0.15rem !important;
    }
    [data-testid="stSidebarNav"] ul {
        margin-top: 0 !important;
        padding-top: 0 !important;
    }
</style>
"""


def logo_exists() -> bool:
    return LOGO_PATH.is_file()


def show_sidebar_branding():
    """Logo na barra lateral, acima dos links das páginas."""
    from services.auth import is_admin, is_logged_in, show_auth_controls_sidebar

    st.markdown(_SIDEBAR_LOGO_FIRST_CSS, unsafe_allow_html=True)
    with st.sidebar:
        if logo_exists():
            st.image(str(LOGO_PATH), width="stretch")
            st.markdown(
                '<hr style="margin:0.2rem 0 0.15rem 0;border:none;border-top:1px solid rgba(0,0,0,0.10);">',
                unsafe_allow_html=True,
            )
        show_auth_controls_sidebar()

        # Perfil cadastro: menu lateral igual ao admin no HTML, mas só vê links permitidos
        # (app + Cadastro + OTB). Financeiro e Usuários ficam ocultos via CSS.
        if is_logged_in() and not is_admin():
            st.markdown(
                """
<style>
[data-testid="stSidebarNav"] li:has(a[href*="Dashboard_Financeiro"]),
[data-testid="stSidebarNav"] li:has(a[href*="dashboard_financeiro"]),
[data-testid="stSidebarNav"] li:has(a[href*="Meta_Fluxo_Caixa"]),
[data-testid="stSidebarNav"] li:has(a[href*="meta_fluxo_caixa"]),
[data-testid="stSidebarNav"] li:has(a[href*="Admin_usuarios"]),
[data-testid="stSidebarNav"] li:has(a[href*="admin_usuarios"]) {
    display: none !important;
}
</style>
""",
                unsafe_allow_html=True,
            )


def show_home_logo_centered():
    """Logo centralizada na página inicial (acima do título)."""
    if not logo_exists():
        return
    _, col, _ = st.columns([1, 2.4, 1])
    with col:
        st.image(str(LOGO_PATH), width="stretch")
