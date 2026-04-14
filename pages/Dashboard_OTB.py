import streamlit as st
import pandas as pd
from services.supabase_client import (
    atualizar_pedido_recebimento,
    buscar_pedido_ids_por_descricao,
    data_baixa_hoje_iso,
    fetch_otb_pipeline,
    listar_pedidos_resumo,
)
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
    value=False,
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
ano_sel = col5.multiselect("Ano", sorted(df["mes"].dt.year.dropna().unique()))
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
# CONTROLE DE RECEBIMENTO (PEDIDOS)
# =========================
@st.cache_data(ttl=60, show_spinner=False)
def carregar_pedidos_recebimento():
    return pd.DataFrame(listar_pedidos_resumo())


st.subheader("📬 Controle de recebimento")
st.caption(
    "Só aparecem pedidos **pendentes de recebimento**. Ao marcar **Recebido** e salvar, gravamos automaticamente "
    "a **data de hoje** (fuso Brasil) e o pedido some desta lista e do OTB “em aberto”. "
    "Todos os filtros acima limitam a lista."
)

ped_rcv = carregar_pedidos_recebimento()
if ped_rcv.empty:
    st.info("Nenhum pedido cadastrado.")
else:
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

    if "recebido" not in ped_rcv.columns:
        ped_rcv["recebido"] = False
    else:
        ped_rcv["recebido"] = ped_rcv["recebido"].fillna(False).astype(bool)

    ped_rcv["data_chegada"] = pd.to_datetime(ped_rcv["data_chegada"], errors="coerce")
    if ano_sel:
        ped_rcv = ped_rcv[ped_rcv["data_chegada"].dt.year.isin(ano_sel)]
    if mes_sel:
        ped_rcv = ped_rcv[ped_rcv["data_chegada"].dt.month.isin(mes_sel)]
    ped_rcv = ped_rcv.loc[~ped_rcv["recebido"]]
    ped_show = ped_rcv.sort_values("id", ascending=False)[
        [
            "id",
            "fornecedor",
            "grupo",
            "marca",
            "data_chegada",
            "total_valor",
            "recebido",
        ]
    ].copy()

    if ped_show.empty:
        st.info("Nenhum pedido pendente de recebimento no filtro atual.")
    else:

        edited_rcv = st.data_editor(
            ped_show,
            column_config={
                "id": st.column_config.NumberColumn("ID pedido", disabled=True, format="%d"),
                "fornecedor": st.column_config.TextColumn("Fornecedor", disabled=True),
                "grupo": st.column_config.TextColumn("Grupo", disabled=True),
                "marca": st.column_config.TextColumn("Marca", disabled=True),
                "data_chegada": st.column_config.DateColumn(
                    "Previsão chegada", disabled=True, format="DD/MM/YYYY"
                ),
                "total_valor": st.column_config.NumberColumn("Total (R$)", disabled=True, format="%.2f"),
                "recebido": st.column_config.CheckboxColumn("Recebido"),
            },
            hide_index=True,
            width="stretch",
            key="editor_recebimento_otb",
            num_rows="fixed",
        )

        if st.button("💾 Salvar recebimentos", key="salvar_receb_otb"):
            try:
                alteradas = 0
                for _, r in edited_rcv.iterrows():
                    orig = ped_show.loc[ped_show["id"] == r["id"]].iloc[0]
                    rec_ant = bool(orig["recebido"])
                    rec_novo = bool(r["recebido"])
                    if rec_ant == rec_novo:
                        continue
                    dr = data_baixa_hoje_iso() if rec_novo else None
                    atualizar_pedido_recebimento(int(r["id"]), rec_novo, data_recebimento=dr)
                    alteradas += 1

                carregar_pedidos_recebimento.clear()
                carregar_otb.clear()
                if alteradas:
                    st.success(
                        f"Atualizado: {alteradas} registro(s). "
                        "**Data de recebimento** gravada como a **data de hoje** (Brasil)."
                    )
                else:
                    st.info("Nenhuma alteração.")
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

df_base = _df_otb_tree.groupby(
    ["grupo", "marca", "referencia"],
    as_index=False,
    dropna=False,
).agg(
    {
        "total_qtd": "sum",
        "total_valor": "sum",
        "data_recebimento": "max",
    }
)

total_geral = df_base["total_valor"].sum()

if total_geral == 0:
    df_base["perc"] = 0
else:
    df_base["perc"] = df_base["total_valor"] / total_geral

# =========================
# 🧠 TRANSFORMA EM HIERARQUIA
# =========================
def build_tree(df):
    data = []

    for grupo, df_g in df.groupby("grupo", dropna=False):
        node_g = {
            "Grupo": str(grupo),
            "Quantidade": float(df_g["total_qtd"].sum()),
            "Valor": float(df_g["total_valor"].sum()),
            "% Participação": float(df_g["total_valor"].sum() / total_geral) if total_geral else 0,
            "Data_do_recebimento": _fmt_data_recebimento_otb(df_g["data_recebimento"].max()),
            "children": [],
        }

        for marca, df_m in df_g.groupby("marca", dropna=False):
            node_m = {
                "Grupo": str(marca),
                "Quantidade": float(df_m["total_qtd"].sum()),
                "Valor": float(df_m["total_valor"].sum()),
                "% Participação": float(df_m["total_valor"].sum() / total_geral) if total_geral else 0,
                "Data_do_recebimento": _fmt_data_recebimento_otb(df_m["data_recebimento"].max()),
                "children": [],
            }

            for _, r in df_m.iterrows():
                node_m["children"].append(
                    {
                        "Grupo": str(r["referencia"]),
                        "Quantidade": float(r["total_qtd"]),
                        "Valor": float(r["total_valor"]),
                        "% Participação": float(r["perc"]),
                        "Data_do_recebimento": _fmt_data_recebimento_otb(r["data_recebimento"]),
                    }
                )

            node_g["children"].append(node_m)

        data.append(node_g)

    return data

tree_data = build_tree(df_base)

# =========================
# 🔥 CONVERTE PARA PATH STRING
# =========================
def flatten_tree(data, parent=None):
    if parent is None:
        parent = []

    rows = []

    for item in data:
        current_path = parent + [str(item["Grupo"])]
        path_str = "||".join(current_path)

        rows.append(
            {
                "path": path_str,
                "Grupo": str(item["Grupo"]),
                "Quantidade": float(item["Quantidade"]),
                "Valor": float(item["Valor"]),
                "Data_do_recebimento": item.get("Data_do_recebimento") or "",
            }
        )

        if "children" in item:
            rows.extend(flatten_tree(item["children"], current_path))

    return rows

df_tree = pd.DataFrame(flatten_tree(tree_data))
if df_tree.empty:
    df_tree = pd.DataFrame(
        columns=["path", "Grupo", "Quantidade", "Valor", "Data_do_recebimento"]
    )

# =========================
# 🎨 GRID CONFIG - DRILL
# =========================
gridOptions = {
    "treeData": True,
    "animateRows": True,
    "groupDefaultExpanded": 0,

    "getDataPath": JsCode("""
        function(data) {
            return String(data.path).split("||");
        }
    """),

    "autoGroupColumnDef": {
        "headerName": "Grupo / Marca / Referência",
        "field": "Grupo",
        "minWidth": 420,
        "pinned": "left",
        "cellStyle": {
            "textAlign": "center"
        },
        "headerClass": "ag-center-header",
        "cellRendererParams": {
            "suppressCount": True
        }
    },

    "columnDefs": [
        {
            "field": "Quantidade",
            "headerName": "Quantidade",
            "type": "numericColumn",
            "cellStyle": {
                "textAlign": "center"
            },
            "headerClass": "ag-center-header",
            "valueFormatter": JsCode("""
                function(params) {
                    if (params.value == null) return '';
                    return Number(params.value).toLocaleString('pt-BR');
                }
            """)
        },
        {
            "field": "Valor",
            "headerName": "Valor",
            "type": "numericColumn",
            "cellStyle": {
                "textAlign": "center"
            },
            "headerClass": "ag-center-header",
            "valueFormatter": JsCode("""
                function(params) {
                    if (params.value == null) return '';
                    return Number(params.value).toLocaleString('pt-BR', {
                        style: 'currency',
                        currency: 'BRL'
                    });
                }
            """)
        },
        {
            "field": "Data_do_recebimento",
            "headerName": "Data do recebimento",
            "cellStyle": {"textAlign": "center"},
            "headerClass": "ag-center-header",
            "valueFormatter": JsCode("""
                function(params) {
                    if (params.value == null || params.value === '') return '';
                    return String(params.value);
                }
            """),
        },
    ],

    "defaultColDef": {
        "resizable": True,
        "sortable": True,
        "filter": True,
        "flex": 1
    }
}


st.markdown("""
<style>
.ag-center-header .ag-header-cell-label {
    justify-content: center !important;
}
</style>
""", unsafe_allow_html=True)

st.subheader(
    "📑 OTB hierárquico (em aberto)"
    if not incluir_recebidos_otb
    else "📑 OTB hierárquico (completo)"
)
if not incluir_recebidos_otb:
    st.caption(
        "Padrão: só **não recebidos**; a data fica em branco até haver recebimento. "
        "Se faltar um grupo do cadastro, ele pode estar só em pedidos **já recebidos** — use a opção no topo."
    )
else:
    st.caption(
        "Inclui recebidos: **Data do recebimento** mostra a data salva no pedido (valor mais recente no agregado)."
    )

# =========================
# 🚀 AGGRID
# =========================
AgGrid(
    df_tree,
    gridOptions=gridOptions,
    enable_enterprise_modules=True,
    fit_columns_on_grid_load=False,
    height=550,
    allow_unsafe_jscode=True,
    theme="balham"
)

# =========================
# 💾 EXPORTA EXCEL
# =========================
def exportar_excel_otb(df_tree):
    import io
    import pandas as pd

    output = io.BytesIO()

    df_export = df_tree.copy()
    df_export["path"] = df_export["path"].fillna("").astype(str)

    split_cols = (
        df_export["path"]
        .str.split("||", expand=True, regex=False)
        .reindex(columns=range(3))
    )

    split_cols.columns = ["Grupo_export", "Marca", "Referencia"]

    df_export = pd.concat([df_export, split_cols], axis=1)

    df_export = df_export[df_export["Referencia"].notna()]

    if "Data_do_recebimento" not in df_export.columns:
        df_export["Data_do_recebimento"] = ""

    df_export = df_export[
        ["Grupo_export", "Marca", "Referencia", "Data_do_recebimento", "Quantidade", "Valor"]
    ].rename(
        columns={
            "Grupo_export": "Grupo",
            "Data_do_recebimento": "Data do recebimento",
        }
    )

    df_export["Quantidade"] = (
        pd.to_numeric(df_export["Quantidade"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    df_export["Valor"] = (
        pd.to_numeric(df_export["Valor"], errors="coerce")
        .fillna(0.0)
    )

    df_export = df_export.sort_values(
        ["Grupo", "Marca", "Referencia"]
    )

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_export.to_excel(writer, index=False, sheet_name="OTB")

        workbook = writer.book
        worksheet = writer.sheets["OTB"]

        formato_moeda = workbook.add_format({
            "num_format": 'R$ #,##0.00'
        })

        worksheet.set_column("A:C", 22)
        worksheet.set_column("D:D", 18)
        worksheet.set_column("E:E", 15)
        worksheet.set_column("F:F", 18, formato_moeda)

    return output.getvalue()

excel_file = exportar_excel_otb(df_tree)

st.download_button(
    label="📥 Exportar Excel",
    data=excel_file,
    file_name="otb_detalhado.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)