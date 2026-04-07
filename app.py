import streamlit as st

from services.branding import show_home_logo_centered, show_sidebar_branding

st.set_page_config(
    page_title="Controle de OTB e Fluxo de Caixa",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
    /* Títulos dos cards em uma linha (telas largas); em mobile pode quebrar */
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

col1, col2, col3 = st.columns(3, gap="large")

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

st.markdown(
    """
    <p class="home-footnote">
        Você também pode usar o menu <strong>⋮</strong> no canto superior esquerdo
        para navegar entre as páginas.
    </p>
    """,
    unsafe_allow_html=True,
)
