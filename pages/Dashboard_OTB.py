import streamlit as st
import pandas as pd
from services.supabase_client import (
    atualizar_item_recebimento,
    atualizar_pedido_recebimento,
    buscar_pedido_ids_por_descricao,
    data_baixa_hoje_iso,
    fetch_otb_pipeline,
    listar_itens_pedido,
    listar_pedidos_resumo,
    sincronizar_recebimento_pedido,
)
try:
    from services.supabase_client import buscar_pedido_ids_por_referencia
except ImportError:
    # Fallback para sessões antigas do Streamlit sem recarga completa do módulo.
    def buscar_pedido_ids_por_referencia(referencias):
        return set()
try:
    from services.supabase_client import buscar_pedido_ids_com_itens_recebidos
except ImportError:
    # Fallback para sessões antigas do Streamlit sem recarga completa do módulo.
    def buscar_pedido_ids_com_itens_recebidos():
        return set()
from services.branding import show_sidebar_branding
import plotly.express as px
import locale

try:
    locale.setlocale(locale.LC_ALL, "pt_BR.UTF-8")
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, "Portuguese_Brazil.1252")
    except locale.Error:
        pass
import io
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import JsCode
import pandas as pd
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def formatar_moeda_br(valor):
    if pd.isna(valor):
        return ""
    return (
        f"R$ {float(valor):,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


st.set_page_config(page_title="OTB", layout="wide")

from services.auth import require_login

require_login()

show_sidebar_branding()

st.title("📦 OTB - Planejamento de Compras")

incluir_recebidos_otb = st.checkbox(
    "Incluir pedidos **já recebidos** nos totais, gráficos e hierarquia OTB",
    value=True,
    key="otb_incluir_recebidos",
    help="Desligado (padrão): só pedidos ainda não recebidos. Se um grupo (ex.: Masculino) sumiu, "
    "pode ser porque todos os pedidos desse grupo já foram marcados como recebidos — ligue esta opção para vê-los de novo.",
)

# =========================
# 🔌 CARREGAR DADOS (LEVE)
# =========================
@st.cache_data(ttl=300, show_spinner=False)
def carregar_otb(incluir_recebidos: bool):
    return fetch_otb_pipeline(somente_nao_recebidos=not incluir_recebidos)


df = carregar_otb(incluir_recebidos_otb)

# Normaliza textos para evitar duplicidades por espaços extras no legado.
def _norm_txt(v):
    return " ".join(str(v or "").split())

for _c in ("grupo", "marca", "referencia", "descricao"):
    if _c in df.columns:
        df[_c] = df[_c].map(_norm_txt)

# =========================
# 🔄 TRATAMENTO MÍNIMO
# =========================
if df.empty:
    if incluir_recebidos_otb:
        st.info("Não há itens de pedido para montar o OTB (cadastre itens nos pedidos).")
    else:
        st.info(
            "**OTB em aberto** está vazio: não há itens em pedidos **pendentes** de recebimento, "
            "ou todos os pedidos já foram marcados como **Recebidos**. "
            "Para ver também grupos só com pedido já recebido (ex.: Masculino), marque a opção acima."
        )
    df = pd.DataFrame(
        columns=[
            "grupo",
            "marca",
            "referencia",
            "descricao",
            "mes",
            "total_qtd",
            "total_valor",
            "data_recebimento",
        ]
    )
    df["mes"] = pd.Series(dtype="datetime64[ns]")
    df["mes_ano"] = pd.Series(dtype=object)
else:
    df["mes"] = pd.to_datetime(df["mes"])
    df["mes_ano"] = df["mes"].dt.strftime("%m/%Y")
    if "descricao" not in df.columns:
        df["descricao"] = ""
    df["descricao"] = df["descricao"].fillna("").astype(str).str.strip()
    if "data_recebimento" not in df.columns:
        df["data_recebimento"] = pd.NaT
    else:
        df["data_recebimento"] = pd.to_datetime(df["data_recebimento"], errors="coerce")

# =========================
# 🔎 FILTROS (LEVES)
# =========================
st.subheader("🔎 Filtros")

col1, col2, col3, col4, col5, col6 = st.columns(6)

grupo_sel = col1.multiselect("Grupo", sorted(df["grupo"].dropna().unique()))
marca_sel = col2.multiselect("Marca", sorted(df["marca"].dropna().unique()))
ref_sel = col3.multiselect("Referência", sorted(df["referencia"].dropna().unique()))
desc_opcoes = sorted(df.loc[df["descricao"] != "", "descricao"].unique())
desc_sel = col4.multiselect("Descrição", desc_opcoes)
anos_disponiveis = sorted(int(a) for a in df["mes"].dt.year.dropna().unique())
ano_atual = pd.Timestamp.now().year
anos_default = [a for a in anos_disponiveis if a >= ano_atual]
if not anos_default and anos_disponiveis:
    anos_default = [max(anos_disponiveis)]
ano_sel = col5.multiselect("Ano", anos_disponiveis, default=anos_default)
mes_sel = col6.multiselect("Mês", sorted(df["mes"].dt.month.dropna().unique()))

# =========================
# 🔍 APLICA FILTRO
# =========================
df_filtrado = df.copy()

if grupo_sel:
    df_filtrado = df_filtrado[df_filtrado["grupo"].isin(grupo_sel)]

if marca_sel:
    df_filtrado = df_filtrado[df_filtrado["marca"].isin(marca_sel)]

if ref_sel:
    df_filtrado = df_filtrado[df_filtrado["referencia"].isin(ref_sel)]

if desc_sel:
    df_filtrado = df_filtrado[df_filtrado["descricao"].isin(desc_sel)]

if ano_sel:
    df_filtrado = df_filtrado[df_filtrado["mes"].dt.year.isin(ano_sel)]

if mes_sel:
    df_filtrado = df_filtrado[df_filtrado["mes"].dt.month.isin(mes_sel)]

if incluir_recebidos_otb:
    st.caption(
        "Visão **completa**: pedidos recebidos e pendentes. **Data do recebimento** na hierarquia "
        "preenche quando todas as linhas daquele recorte têm data gravada. **Mês** = previsão de chegada."
    )
else:
    st.caption(
        "Somente pedidos **ainda não recebidos** (padrão). Grupos só com pedido já recebido **não aparecem**. "
        "**Mês** = previsão de chegada (`data_chegada`)."
    )

# =========================
# CONTROLE DE RECEBIMENTO (PARCIAL POR ITEM)
# =========================
@st.cache_data(ttl=60, show_spinner=False)
def carregar_pedidos_recebimento():
    return pd.DataFrame(listar_pedidos_resumo())


st.subheader("📬 Controle de recebimento")
st.caption(
    "Selecione um pedido para ver seus itens e marcar quais foram recebidos. "
    "Quando todos os itens forem marcados, o pedido fecha automaticamente."
)

ped_rcv = carregar_pedidos_recebimento()
if ped_rcv.empty:
    st.info("Nenhum pedido cadastrado.")
else:
    for _c in ("grupo", "marca", "fornecedor"):
        if _c in ped_rcv.columns:
            ped_rcv[_c] = ped_rcv[_c].map(_norm_txt)

    if grupo_sel:
        ped_rcv = ped_rcv[ped_rcv["grupo"].isin(grupo_sel)]
    if marca_sel:
        ped_rcv = ped_rcv[ped_rcv["marca"].isin(marca_sel)]
    if desc_sel:
        ids_com_desc = buscar_pedido_ids_por_descricao(desc_sel)
        if ids_com_desc:
            ped_rcv = ped_rcv[ped_rcv["id"].isin(ids_com_desc)]
        else:
            ped_rcv = ped_rcv.iloc[0:0]
    if ref_sel:
        ids_com_ref = buscar_pedido_ids_por_referencia(ref_sel)
        if ids_com_ref:
            ped_rcv = ped_rcv[ped_rcv["id"].isin(ids_com_ref)]
        else:
            ped_rcv = ped_rcv.iloc[0:0]

    if "recebido" not in ped_rcv.columns:
        ped_rcv["recebido"] = False
    else:
        ped_rcv["recebido"] = ped_rcv["recebido"].fillna(False).astype(bool)

    ped_rcv["data_chegada"] = pd.to_datetime(ped_rcv["data_chegada"], errors="coerce")
    if ano_sel:
        ped_rcv = ped_rcv[ped_rcv["data_chegada"].dt.year.isin(ano_sel)]
    if mes_sel:
        ped_rcv = ped_rcv[ped_rcv["data_chegada"].dt.month.isin(mes_sel)]

    ver_recebidos = st.checkbox(
        "Mostrar pedidos/itens recebidos (parcial e total)",
        value=False,
        key="rcv_ver_recebidos",
    )
    if ver_recebidos:
        ids_com_item_recebido = buscar_pedido_ids_com_itens_recebidos()
        if ids_com_item_recebido:
            ped_rcv = ped_rcv.loc[ped_rcv["id"].isin(ids_com_item_recebido)]
        else:
            ped_rcv = ped_rcv.iloc[0:0]
    else:
        ped_rcv = ped_rcv.loc[~ped_rcv["recebido"]]
    ped_show = ped_rcv.sort_values("id", ascending=False)

    if ped_show.empty:
        st.info("Nenhum pedido pendente de recebimento no filtro atual.")
    else:
        opcoes = {}
        for _, p in ped_show.iterrows():
            dc = pd.to_datetime(p["data_chegada"], errors="coerce")
            dc_str = dc.strftime("%d/%m/%Y") if pd.notna(dc) else "—"
            opcoes[int(p["id"])] = (
                f"#{int(p['id'])} — {p.get('fornecedor','')} | "
                f"{p.get('grupo','')} / {p.get('marca','')} | "
                f"Chegada: {dc_str} | {formatar_moeda_br(p.get('total_valor', 0))}"
            )

        pid_sel = st.selectbox(
            "Pedido",
            options=list(opcoes.keys()),
            format_func=lambda x: opcoes[x],
            key="sel_pedido_receb",
        )

        if pid_sel:
            itens = listar_itens_pedido(pid_sel)
            if not itens:
                st.info("Nenhum item encontrado para este pedido.")
            else:
                df_itens = pd.DataFrame(itens)
                df_itens["recebido"] = df_itens["recebido"].fillna(False).astype(bool)

                n_total = len(df_itens)
                n_recebidos = int(df_itens["recebido"].sum())
                if n_recebidos > 0:
                    st.caption(f"**{n_recebidos}** de **{n_total}** itens já recebidos")

                if ver_recebidos:
                    df_itens_view = df_itens.loc[df_itens["recebido"]].copy()
                else:
                    df_itens_view = df_itens.loc[~df_itens["recebido"]].copy()

                if df_itens_view.empty:
                    st.info(
                        "Nenhum item para exibir neste modo. "
                        "Altere a opção 'Mostrar pedidos/itens recebidos (parcial e total)'."
                    )
                    edited = pd.DataFrame(
                        columns=["id", "referencia", "descricao", "quantidade", "custo_total", "recebido"]
                    )
                else:
                    edited = st.data_editor(
                        df_itens_view[
                            ["id", "referencia", "descricao", "quantidade", "custo_total", "recebido"]
                        ].copy(),
                    column_config={
                        "id": st.column_config.NumberColumn("ID", disabled=True, format="%d", width="small"),
                        "referencia": st.column_config.TextColumn("Referência", disabled=True),
                        "descricao": st.column_config.TextColumn("Descrição", disabled=True),
                        "quantidade": st.column_config.NumberColumn("Qtd", disabled=True, format="%d", width="small"),
                        "custo_total": st.column_config.NumberColumn("Valor (R$)", disabled=True, format="%.2f"),
                        "recebido": st.column_config.CheckboxColumn("Recebido"),
                    },
                    hide_index=True,
                    width="stretch",
                    key=f"editor_itens_{pid_sel}",
                    num_rows="fixed",
                    )

                col_salvar, col_todos = st.columns(2)
                if col_salvar.button("💾 Salvar recebimento", key="salvar_itens_rcv"):
                    try:
                        def _to_bool(v):
                            if isinstance(v, bool):
                                return v
                            if pd.isna(v):
                                return False
                            if isinstance(v, (int, float)):
                                return bool(int(v))
                            s = str(v).strip().lower()
                            return s in ("1", "true", "t", "yes", "sim")

                        alteradas = 0
                        orig_por_id = (
                            df_itens.set_index("id")[["recebido", "data_recebimento"]].to_dict("index")
                        )
                        desejado_por_id = {}
                        for _, row in edited.iterrows():
                            item_id = int(row["id"])
                            novo_receb = _to_bool(row["recebido"])
                            desejado_por_id[item_id] = novo_receb
                            orig = orig_por_id.get(item_id)
                            if orig is None:
                                continue
                            orig_receb = _to_bool(orig.get("recebido"))
                            orig_data = orig.get("data_recebimento")
                            precisa_preencher_data = novo_receb and (pd.isna(orig_data) or orig_data is None)
                            if orig_receb == novo_receb and not precisa_preencher_data:
                                continue
                            dr = data_baixa_hoje_iso() if novo_receb else None
                            atualizar_item_recebimento(item_id, novo_receb, dr)
                            alteradas += 1

                        itens_pos = listar_itens_pedido(pid_sel)
                        falhas = []
                        for r in itens_pos:
                            iid = int(r.get("id"))
                            if iid not in desejado_por_id:
                                continue
                            receb_persistido = _to_bool(r.get("recebido"))
                            if receb_persistido != desejado_por_id[iid]:
                                falhas.append(iid)
                        if falhas:
                            st.error(
                                "Alguns itens não foram persistidos no banco. "
                                f"IDs: {', '.join(str(x) for x in falhas[:8])}"
                            )
                            st.stop()

                        if alteradas:
                            sincronizar_recebimento_pedido(pid_sel)
                            carregar_pedidos_recebimento.clear()
                            carregar_otb.clear()
                            st.success(f"{alteradas} item(ns) atualizado(s).")
                        else:
                            st.info("Nenhuma alteração.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

                if col_todos.button("✅ Receber todos os itens", key="todos_itens_rcv"):
                    try:
                        hoje = data_baixa_hoje_iso()
                        for item in itens:
                            if not item.get("recebido", False):
                                atualizar_item_recebimento(int(item["id"]), True, hoje)
                        sincronizar_recebimento_pedido(pid_sel)
                        carregar_pedidos_recebimento.clear()
                        carregar_otb.clear()
                        st.success("Todos os itens marcados como recebidos.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {e}")

# =========================
# 📊 KPIs
# =========================
total_qtd = df_filtrado["total_qtd"].sum()
total_valor = df_filtrado["total_valor"].sum()
n_linhas = len(df_filtrado)
meses_distintos = df_filtrado["mes"].nunique()
preco_medio_un = total_valor / total_qtd if total_qtd > 0 else 0
media_mensal_valor = total_valor / meses_distintos if meses_distintos else 0
media_mensal_qtd = total_qtd / meses_distintos if meses_distintos else 0
grupos_ativos = df_filtrado["grupo"].nunique()
marcas_ativas = df_filtrado["marca"].nunique()

st.markdown(
    """
    <style>
    div[data-testid="stMetric"] {
        min-width: 0;
        padding: 0.85rem 0.65rem;
        background-color: rgba(250, 250, 250, 0.6);
        border-radius: 0.5rem;
        border: 1px solid rgba(0, 0, 0, 0.06);
    }
    div[data-testid="stMetric"] label[data-testid="stMetricLabel"] p {
        font-size: 0.85rem;
        white-space: normal;
        line-height: 1.25;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-size: clamp(0.95rem, 2vw, 1.3rem);
        white-space: nowrap;
        overflow: visible;
        text-overflow: clip;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

r1c1, r1c2, r1c3, r1c4 = st.columns(4)
r1c1.metric("📦 Total quantidade", f"{int(total_qtd):,}".replace(",", "."))
r1c2.metric("💰 Total comprado", formatar_moeda_br(total_valor))
r1c3.metric("🏷️ Preço médio / unidade", formatar_moeda_br(preco_medio_un))
r1c4.metric("📅 Média mensal (valor)", formatar_moeda_br(media_mensal_valor))

r2c1, r2c2, r2c3, r2c4 = st.columns(4)
r2c1.metric("📆 Média mensal (qtd)", f"{int(round(media_mensal_qtd)):,}".replace(",", "."))
r2c2.metric("📑 Registros no período", f"{int(n_linhas):,}".replace(",", "."))
r2c3.metric("🗂️ Grupos ativos", f"{int(grupos_ativos):,}".replace(",", "."))
r2c4.metric("🏪 Marcas ativas", f"{int(marcas_ativas):,}".replace(",", "."))

# =========================
# 📊 GRÁFICOS
# =========================
st.subheader("📊 Indicadores OTB")

if df_filtrado.empty:
    st.info("Sem linhas de OTB em aberto para este filtro.")
else:
    df_top_m = (
        df_filtrado.groupby("marca", as_index=False)
        .agg(total_valor=("total_valor", "sum"))
        .dropna(subset=["marca"])
        .nlargest(12, "total_valor")
    )
    df_top_g = (
        df_filtrado.groupby("grupo", as_index=False)
        .agg(total_valor=("total_valor", "sum"))
        .dropna(subset=["grupo"])
        .nlargest(12, "total_valor")
    )

    g3, g4 = st.columns(2)
    with g3:
        if not df_top_m.empty:
            fig_tm = px.bar(
                df_top_m,
                x="total_valor",
                y="marca",
                orientation="h",
                text="total_valor",
                labels={"total_valor": "Valor (R$)", "marca": "Marca"},
            )
            fig_tm.update_traces(
                texttemplate="R$ %{text:,.0f}",
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>R$ %{x:,.2f}<extra></extra>",
            )
            fig_tm.update_layout(
                title="Top marcas por valor",
                yaxis=dict(categoryorder="total ascending"),
                margin=dict(l=8, r=80, t=48, b=8),
            )
            st.plotly_chart(fig_tm, width="stretch")
        else:
            st.info("Sem dados de marca para o período.")

    with g4:
        if not df_top_g.empty:
            fig_tg = px.bar(
                df_top_g,
                x="total_valor",
                y="grupo",
                orientation="h",
                text="total_valor",
                labels={"total_valor": "Valor (R$)", "grupo": "Grupo"},
            )
            fig_tg.update_traces(
                texttemplate="R$ %{text:,.0f}",
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>R$ %{x:,.2f}<extra></extra>",
            )
            fig_tg.update_layout(
                title="Top grupos por valor",
                yaxis=dict(categoryorder="total ascending"),
                margin=dict(l=8, r=80, t=48, b=8),
            )
            st.plotly_chart(fig_tg, width="stretch")
        else:
            st.info("Sem dados de grupo para o período.")

    df_marca_share = (
        df_filtrado.groupby("marca", as_index=False)
        .agg(total_valor=("total_valor", "sum"))
        .dropna(subset=["marca"])
    )

    df_desc_bar = (
        df_filtrado.loc[df_filtrado["descricao"] != ""]
        .groupby("descricao", as_index=False)
        .agg(total_valor=("total_valor", "sum"))
        .nlargest(12, "total_valor")
    )

    g_pie, g_desc = st.columns(2)

    with g_pie:
        if not df_marca_share.empty:
            df_marca_share = df_marca_share.sort_values("total_valor", ascending=False)
            top_n = 8
            if len(df_marca_share) > top_n:
                outros = df_marca_share.iloc[top_n:]["total_valor"].sum()
                df_marca_share = pd.concat(
                    [
                        df_marca_share.head(top_n),
                        pd.DataFrame([{"marca": "Outros", "total_valor": outros}]),
                    ],
                    ignore_index=True,
                )
            fig_pie = px.pie(
                df_marca_share,
                values="total_valor",
                names="marca",
                title="Participação do valor por marca",
                hole=0.35,
            )
            fig_pie.update_traces(
                textposition="inside",
                textinfo="percent+label",
                hovertemplate="<b>%{label}</b><br>R$ %{value:,.2f}<br>%{percent}<extra></extra>",
            )
            st.plotly_chart(fig_pie, width="stretch")

    with g_desc:
        if not df_desc_bar.empty:
            fig_desc = px.bar(
                df_desc_bar,
                x="total_valor",
                y="descricao",
                orientation="h",
                text="total_valor",
                labels={"total_valor": "Valor (R$)", "descricao": "Descrição"},
            )
            fig_desc.update_traces(
                texttemplate="R$ %{text:,.0f}",
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>R$ %{x:,.2f}<extra></extra>",
            )
            fig_desc.update_layout(
                title="Top descrições por valor",
                yaxis=dict(categoryorder="total ascending"),
                margin=dict(l=8, r=80, t=48, b=8),
            )
            st.plotly_chart(fig_desc, width="stretch")
        else:
            st.info("Sem dados de descrição para o período.")

# =========================
# 📋 GRUPO
# =========================


# =========================
# 📊 BASE
# =========================
def _fmt_data_recebimento_otb(x):
    if x is None:
        return ""
    t = pd.Timestamp(x)
    return "" if pd.isna(t) else t.strftime("%d/%m/%Y")


_df_otb_tree = df_filtrado.copy()
if "data_recebimento" not in _df_otb_tree.columns:
    _df_otb_tree["data_recebimento"] = pd.NaT
for _col, _fallback in (
    ("grupo", "(Sem grupo)"),
    ("marca", "(Sem marca)"),
    ("referencia", "(Sem referência)"),
):
    if _col in _df_otb_tree.columns:
        _df_otb_tree[_col] = (
            _df_otb_tree[_col]
            .astype(object)
            .where(_df_otb_tree[_col].notna(), _fallback)
            .astype(str)
            .str.strip()
            .replace("", _fallback)
        )

if "pedido_ids" not in _df_otb_tree.columns:
    _df_otb_tree["pedido_ids"] = [[] for _ in range(len(_df_otb_tree))]
else:
    _df_otb_tree["pedido_ids"] = _df_otb_tree["pedido_ids"].apply(
        lambda x: x if isinstance(x, list) else []
    )

def _merge_pedido_ids(series):
    ids = set()
    for v in series:
        if isinstance(v, list):
            ids.update(v)
    return sorted(ids)

df_base = _df_otb_tree.groupby(
    ["grupo", "marca", "referencia"],
    as_index=False,
    dropna=False,
).agg(
    {
        "total_qtd": "sum",
        "total_valor": "sum",
        "data_recebimento": "max",
        "pedido_ids": _merge_pedido_ids,
    }
)

total_geral = df_base["total_valor"].sum()

if total_geral == 0:
    df_base["perc"] = 0
else:
    df_base["perc"] = df_base["total_valor"] / total_geral

st.subheader("📑 OTB hierárquico")
if not incluir_recebidos_otb:
    st.caption(
        "Exibindo somente itens pendentes de recebimento."
    )
else:
    st.caption(
        "Exibindo itens pendentes e recebidos; referências recebidas mostram a data ao lado."
    )

# =========================
# 🚀 DRILL-DOWN HIERÁRQUICO
# =========================
if df_base.empty:
    st.info("Sem dados para exibir na hierarquia.")
else:
    def _metric_line(qtd, valor, perc, data_rec=""):
        parts = [
            f"**Qtd:** {int(qtd):,}".replace(",", "."),
            f"**Valor:** {formatar_moeda_br(valor)}",
            f"**Part.:** {perc*100:.1f}%",
        ]
        if data_rec:
            parts.append(f"**Receb.:** {data_rec}")
        return " &nbsp;|&nbsp; ".join(parts)

    for grupo, df_g in sorted(df_base.groupby("grupo", dropna=False), key=lambda x: str(x[0])):
        g_qtd = df_g["total_qtd"].sum()
        g_val = df_g["total_valor"].sum()
        g_perc = g_val / total_geral if total_geral else 0
        g_data = _fmt_data_recebimento_otb(df_g["data_recebimento"].max())
        g_label = f"**{grupo}** — {formatar_moeda_br(g_val)}  ({g_perc*100:.1f}%)"

        with st.expander(g_label, expanded=False):
            st.markdown(_metric_line(g_qtd, g_val, g_perc, g_data))
            st.divider()

            for marca, df_m in sorted(df_g.groupby("marca", dropna=False), key=lambda x: str(x[0])):
                m_qtd = df_m["total_qtd"].sum()
                m_val = df_m["total_valor"].sum()
                m_perc = m_val / total_geral if total_geral else 0
                m_data = _fmt_data_recebimento_otb(df_m["data_recebimento"].max())
                m_label = f"🏷️ {marca} — {formatar_moeda_br(m_val)}  ({m_perc*100:.1f}%)"

                with st.expander(m_label, expanded=False):
                    df_refs = df_m[["referencia", "total_qtd", "total_valor", "perc", "data_recebimento", "pedido_ids"]].copy()
                    df_refs = df_refs.sort_values("referencia")
                    df_refs["data_recebimento"] = df_refs["data_recebimento"].apply(_fmt_data_recebimento_otb)
                    df_refs["pedido_ids"] = df_refs["pedido_ids"].apply(
                        lambda ids: ", ".join(f"#{i}" for i in ids) if isinstance(ids, list) and ids else ""
                    )
                    df_refs = df_refs.rename(columns={
                        "referencia": "Referência",
                        "total_qtd": "Quantidade",
                        "total_valor": "Valor (R$)",
                        "perc": "% Part.",
                        "data_recebimento": "Data Receb.",
                        "pedido_ids": "Pedido(s)",
                    })
                    st.dataframe(
                        df_refs,
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "Pedido(s)": st.column_config.TextColumn(width="small"),
                            "Referência": st.column_config.TextColumn(width="medium"),
                            "Quantidade": st.column_config.NumberColumn(format="%d", width="small"),
                            "Valor (R$)": st.column_config.NumberColumn(format="R$ %.2f", width="medium"),
                            "% Part.": st.column_config.NumberColumn(format="%.1f%%", width="small"),
                            "Data Receb.": st.column_config.TextColumn(width="medium"),
                        },
                    )

# =========================
# 💾 EXPORTA EXCEL
# =========================
def exportar_excel_otb(df_base_export):
    output = io.BytesIO()

    df_export = df_base_export.copy()
    df_export = df_export.rename(columns={
        "grupo": "Grupo",
        "marca": "Marca",
        "referencia": "Referência",
        "total_qtd": "Quantidade",
        "total_valor": "Valor",
    })
    if "data_recebimento" in df_export.columns:
        df_export["Data do recebimento"] = df_export["data_recebimento"].apply(_fmt_data_recebimento_otb)
    else:
        df_export["Data do recebimento"] = ""

    if "pedido_ids" in df_export.columns:
        df_export["Pedido(s)"] = df_export["pedido_ids"].apply(
            lambda ids: ", ".join(f"#{i}" for i in ids) if isinstance(ids, list) and ids else ""
        )
    else:
        df_export["Pedido(s)"] = ""

    cols = ["Pedido(s)", "Grupo", "Marca", "Referência", "Data do recebimento", "Quantidade", "Valor"]
    df_export = df_export[[c for c in cols if c in df_export.columns]]

    df_export["Quantidade"] = (
        pd.to_numeric(df_export["Quantidade"], errors="coerce").fillna(0).astype(int)
    )
    df_export["Valor"] = (
        pd.to_numeric(df_export["Valor"], errors="coerce").fillna(0.0)
    )
    df_export = df_export.sort_values(["Grupo", "Marca", "Referência"])

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_export.to_excel(writer, index=False, sheet_name="OTB")
        workbook = writer.book
        worksheet = writer.sheets["OTB"]
        formato_moeda = workbook.add_format({"num_format": 'R$ #,##0.00'})
        worksheet.set_column("A:A", 14)
        worksheet.set_column("B:D", 22)
        worksheet.set_column("E:E", 18)
        worksheet.set_column("F:F", 15)
        worksheet.set_column("G:G", 18, formato_moeda)

    return output.getvalue()

excel_file = exportar_excel_otb(df_base)

st.download_button(
    label="📥 Exportar Excel",
    data=excel_file,
    file_name="otb_detalhado.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)