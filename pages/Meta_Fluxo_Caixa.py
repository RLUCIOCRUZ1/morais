import streamlit as st
import pandas as pd
from datetime import datetime
from services.supabase_client import (
    listar_metas_fluxo_caixa,
    upsert_meta_fluxo_caixa,
    excluir_meta_fluxo_caixa,
)
from services.branding import show_sidebar_branding

NOMES_MES = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)

st.set_page_config(page_title="Meta Fluxo de Caixa", layout="wide")

from services.auth import require_admin

require_admin()

show_sidebar_branding()

st.title("🎯 Meta de Fluxo de Caixa")

if "sucesso_meta" in st.session_state:
    st.success(st.session_state.sucesso_meta)
    del st.session_state.sucesso_meta


@st.cache_data(ttl=60, show_spinner=False)
def _carregar_metas():
    return listar_metas_fluxo_caixa()


def _invalidar_cache_metas():
    _carregar_metas.clear()


def _formatar_moeda(valor):
    if pd.isna(valor):
        return ""
    return (
        f"R$ {float(valor):,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


st.subheader("➕ Cadastrar / Atualizar Meta")
st.caption(
    "Se já existir uma meta para o mês/ano informado, o valor será **atualizado**."
)

with st.form("form_meta", clear_on_submit=True):
    c1, c2, c3 = st.columns([1, 1, 2])
    ano_now = datetime.today().year
    ano = c1.number_input("Ano", min_value=2020, max_value=2040, value=ano_now, step=1)
    mes = c2.selectbox(
        "Mês",
        options=list(range(1, 13)),
        format_func=lambda m: f"{m:02d} — {NOMES_MES[m - 1]}",
        index=datetime.today().month - 1,
    )
    valor = c3.number_input("Valor da meta (R$)", min_value=0.0, format="%.2f", step=1000.0)

    if st.form_submit_button("💾 Salvar meta", type="primary"):
        if valor <= 0:
            st.warning("Informe um valor maior que zero.")
        else:
            try:
                upsert_meta_fluxo_caixa(ano, mes, valor)
                _invalidar_cache_metas()
                st.session_state.sucesso_meta = (
                    f"Meta salva: {NOMES_MES[mes - 1]}/{ano} — {_formatar_moeda(valor)}"
                )
                st.rerun()
            except Exception as e:
                err = str(e)
                st.error(f"Erro ao salvar: {err}")
                if "metas_fluxo_caixa" in err.lower() or "pgrst" in err.lower():
                    st.info(
                        "Execute a migração `supabase/migrations/007_metas_fluxo_caixa.sql` "
                        "no SQL Editor do Supabase."
                    )

st.markdown("---")
st.subheader("📋 Metas cadastradas")

metas = _carregar_metas()

if not metas:
    st.info("Nenhuma meta cadastrada ainda.")
else:
    df_metas = pd.DataFrame(metas)
    df_metas["mes_nome"] = df_metas["mes"].apply(lambda m: NOMES_MES[int(m) - 1])
    df_metas["mes_ano"] = df_metas.apply(
        lambda r: f"{int(r['mes']):02d}/{int(r['ano'])}", axis=1
    )
    df_metas["valor_fmt"] = df_metas["valor"].apply(
        lambda v: _formatar_moeda(float(v))
    )

    df_display = df_metas[["mes_ano", "mes_nome", "valor_fmt"]].rename(
        columns={
            "mes_ano": "Mês/Ano",
            "mes_nome": "Mês",
            "valor_fmt": "Valor da Meta",
        }
    )
    st.dataframe(df_display, hide_index=True, width="stretch")

    st.markdown("---")
    st.subheader("🗑 Excluir meta")

    opcoes_excluir = {
        f"{int(r['mes']):02d}/{int(r['ano'])} — {_formatar_moeda(float(r['valor']))}": r["id"]
        for r in metas
    }
    sel_excluir = st.selectbox("Selecione a meta", list(opcoes_excluir.keys()))
    chk_excluir = st.checkbox("Confirmo a exclusão", key="chk_excluir_meta")

    if st.button(
        "Excluir meta selecionada",
        type="primary",
        disabled=not chk_excluir,
    ):
        if chk_excluir:
            try:
                excluir_meta_fluxo_caixa(opcoes_excluir[sel_excluir])
                _invalidar_cache_metas()
                st.session_state.sucesso_meta = "Meta excluída."
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao excluir: {e}")
