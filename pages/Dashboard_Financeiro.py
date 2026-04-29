import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
from dateutil.relativedelta import relativedelta
import pandas as pd
import plotly.express as px
from services.supabase_client import (
    supabase,
    atualizar_parcela_pago,
    data_baixa_hoje_iso,
    fetch_parcelas_para_financeiro,
    listar_metas_fluxo_caixa,
)
from services.branding import show_sidebar_branding


def formatar_moeda_br(valor):
    if pd.isna(valor):
        return ""
    return (
        f"R$ {float(valor):,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


NOMES_MES = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)


def _label_mes(num):
    if pd.isna(num):
        return ""
    n = int(num)
    return NOMES_MES[n - 1] if 1 <= n <= 12 else str(n)


def _primeiro_ultimo_dia_mes(ref: date) -> tuple[date, date]:
    primeiro = ref.replace(day=1)
    ultimo_d = calendar.monthrange(ref.year, ref.month)[1]
    ultimo = date(ref.year, ref.month, ultimo_d)
    return primeiro, ultimo


ATALHOS_PERIODO_BAIXA_FIN = (
    "Mês atual",
    "Personalizado",
    "Última semana",
    "Últimos 3 meses",
    "Últimos 6 meses",
    "Último ano",
    "Últimos 2 anos",
)


def _intervalo_atalho_baixa_fin(escolha: str, hoje: date) -> tuple[date, date] | None:
    if escolha == "Personalizado":
        return None
    if escolha == "Mês atual":
        return _primeiro_ultimo_dia_mes(hoje)
    if escolha == "Última semana":
        return hoje - timedelta(days=6), hoje
    if escolha == "Últimos 3 meses":
        return hoje - relativedelta(months=3), hoje
    if escolha == "Últimos 6 meses":
        return hoje - relativedelta(months=6), hoje
    if escolha == "Último ano":
        return hoje - relativedelta(years=1), hoje
    if escolha == "Últimos 2 anos":
        return hoje - relativedelta(years=2), hoje
    return None


def _aplicar_atalho_baixa_fin_callback():
    escolha = st.session_state.get("fin_evol_atalho", "Mês atual")
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    r = _intervalo_atalho_baixa_fin(escolha, hoje)
    if r is not None:
        st.session_state["fin_evol_d_ini"], st.session_state["fin_evol_d_fim"] = r


def _marcar_periodo_baixa_personalizado_callback():
    st.session_state["fin_evol_atalho"] = "Personalizado"


def _secao_fin_header(titulo: str, descricao: str, cor: str, fundo_suave: str) -> None:
    st.markdown(
        f"""
        <div style="
            border-left: 4px solid {cor};
            padding: 0.55rem 0 0.55rem 1rem;
            margin: 0 0 0.75rem 0;
            background: {fundo_suave};
            border-radius: 0 10px 10px 0;
        ">
            <p style="margin:0;font-weight:700;font-size:1.12rem;color:#0f172a;letter-spacing:-0.02em;">{titulo}</p>
            <p style="margin:0.4rem 0 0 0;font-size:0.88rem;color:#64748b;line-height:1.45;">{descricao}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _layout_plotly_base(fig, *, altura: int | None = None) -> None:
    u = dict(
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f8fafc",
        font=dict(family="Segoe UI, system-ui, sans-serif", size=12, color="#334155"),
        margin=dict(l=52, r=28, t=52, b=44),
        hoverlabel=dict(bgcolor="white", font_size=12),
    )
    if altura is not None:
        u["height"] = altura
    fig.update_layout(**u)


COR_VENCIMENTO = "#2563eb"
COR_PAGAMENTO = "#059669"

st.set_page_config(page_title="Dashboard Financeiro", layout="wide")

from services.auth import require_admin

require_admin()

show_sidebar_branding()

st.title("💰 Dashboard Financeiro")

# =========================
# CARREGAR DADOS
# =========================
@st.cache_data(ttl=300, show_spinner=False)
def carregar_financeiro():
    raw_parcelas, tem_coluna_pago = fetch_parcelas_para_financeiro()
    pedidos = (
        supabase.table("pedidos")
        .select("id, fornecedor, grupo, marca, data_chegada, total_quantidade, total_valor")
        .execute()
    )

    df_parcelas = pd.DataFrame(raw_parcelas)
    df_pedidos = pd.DataFrame(pedidos.data)

    return df_parcelas, df_pedidos, tem_coluna_pago

df_parcelas, df_pedidos, TEM_COLUNA_PAGO = carregar_financeiro()

# =========================
# VALIDAÇÃO
# =========================
if df_parcelas.empty:
    st.warning("Nenhuma parcela encontrada.")
    st.stop()

if df_pedidos.empty:
    st.warning("Nenhum pedido encontrado.")
    st.stop()

# =========================
# TRATAMENTO
# =========================
df_parcelas["data_pagamento"] = pd.to_datetime(df_parcelas["data_pagamento"], errors="coerce")
df_parcelas["mes"] = df_parcelas["data_pagamento"].dt.to_period("M").dt.to_timestamp()
df_parcelas["mes_ano"] = df_parcelas["mes"].dt.strftime("%m/%Y")

if not TEM_COLUNA_PAGO or "pago" not in df_parcelas.columns:
    df_parcelas["pago"] = False
else:
    df_parcelas["pago"] = df_parcelas["pago"].fillna(False).astype(bool)

if "id" in df_parcelas.columns:
    df_parcelas = df_parcelas.rename(columns={"id": "parcela_id"})
else:
    df_parcelas["parcela_id"] = pd.NA

df_pedidos = df_pedidos.rename(columns={"id": "pedido_db_id"})

df = df_parcelas.merge(
    df_pedidos,
    left_on="pedido_id",
    right_on="pedido_db_id",
    how="left",
)

# Normaliza textos para evitar duplicidades visuais por espaços extras no legado.
def _norm_txt(v):
    return " ".join(str(v or "").split())

for _c in ("grupo", "marca", "fornecedor"):
    if _c in df.columns:
        df[_c] = df[_c].map(_norm_txt)

if "data_quitacao" not in df.columns:
    df["data_quitacao"] = pd.NaT
else:
    df["data_quitacao"] = pd.to_datetime(df["data_quitacao"], errors="coerce")

# =========================
# FILTROS
# =========================
st.subheader("🔎 Filtros gerais")

col1, col2, col3, col4, col5 = st.columns(5)

grupo_sel = col1.multiselect("Grupo", sorted(df["grupo"].dropna().unique()))
marca_sel = col2.multiselect("Marca", sorted(df["marca"].dropna().unique()))
fornecedor_sel = col3.multiselect("Fornecedor", sorted(df["fornecedor"].dropna().unique()))
anos_disponiveis = sorted(int(a) for a in df["data_pagamento"].dt.year.dropna().unique())
ano_atual = pd.Timestamp.now().year
anos_default = [a for a in anos_disponiveis if a >= ano_atual]
if not anos_default and anos_disponiveis:
    anos_default = [max(anos_disponiveis)]
ano_sel = col4.multiselect("Ano", anos_disponiveis, default=anos_default)
meses_opts = sorted({int(m) for m in df["data_pagamento"].dt.month.dropna().unique()})
mes_sel = col5.multiselect(
    "Mês",
    options=meses_opts,
    format_func=_label_mes,
)

df_filtrado = df.copy()

if grupo_sel:
    df_filtrado = df_filtrado[df_filtrado["grupo"].isin(grupo_sel)]

if marca_sel:
    df_filtrado = df_filtrado[df_filtrado["marca"].isin(marca_sel)]

if fornecedor_sel:
    df_filtrado = df_filtrado[df_filtrado["fornecedor"].isin(fornecedor_sel)]

if ano_sel:
    df_filtrado = df_filtrado[df_filtrado["data_pagamento"].dt.year.isin(ano_sel)]

if mes_sel:
    df_filtrado = df_filtrado[df_filtrado["data_pagamento"].dt.month.isin(mes_sel)]

# =========================
# KPIS
# =========================
total_parcelas = len(df_filtrado)
total_valor = df_filtrado["valor_parcela"].sum()
ticket_medio = df_filtrado["valor_parcela"].mean() if total_parcelas > 0 else 0
maior_parcela = df_filtrado["valor_parcela"].max() if total_parcelas > 0 else 0
meses_com_pagamento = df_filtrado["mes"].nunique()
media_mensal = total_valor / meses_com_pagamento if meses_com_pagamento else 0

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
        font-size: clamp(0.95rem, 2.1vw, 1.35rem);
        white-space: nowrap;
        overflow: visible;
        text-overflow: clip;
        word-break: keep-all;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

k1, k2, k3, k4 = st.columns(4)

k1.metric(
    "💰 Valor total (parcelas)",
    formatar_moeda_br(total_valor),
)
k2.metric("📊 Ticket médio", formatar_moeda_br(ticket_medio))
k3.metric("📌 Maior parcela", formatar_moeda_br(maior_parcela))
k4.metric("📅 Média mensal", formatar_moeda_br(media_mensal))

st.caption(
    "Os filtros **Ano** e **Mês** (acima) usam a **data de vencimento** das parcelas. "
    "Os cartões refletem esse mesmo recorte."
)

# =========================
# GRÁFICOS — VENCIMENTO → PAGAMENTO (sequência)
# =========================
st.divider()

_secao_fin_header(
    "1 · Visão por data de vencimento",
    "Compromissos futuros ou planejados: o agrupamento usa a data de vencimento de cada parcela "
    "(e os filtros Ano/Mês do topo). Cor azul nesta seção.",
    COR_VENCIMENTO,
    "rgba(239, 246, 255, 0.92)",
)

# Top fornecedor / marca (mesmo recorte por vencimento)
df_top_f = (
    df_filtrado.groupby("fornecedor", as_index=False)["valor_parcela"]
    .sum()
    .dropna(subset=["fornecedor"])
    .nlargest(12, "valor_parcela")
)
df_top_m = (
    df_filtrado.groupby("marca", as_index=False)["valor_parcela"]
    .sum()
    .dropna(subset=["marca"])
    .nlargest(12, "valor_parcela")
)

g3, g4 = st.columns(2)
with g3:
    if not df_top_f.empty:
        fig_f = px.bar(
            df_top_f,
            x="valor_parcela",
            y="fornecedor",
            orientation="h",
            text="valor_parcela",
            labels={"valor_parcela": "Valor (R$)", "fornecedor": "Fornecedor"},
            color_discrete_sequence=[COR_VENCIMENTO],
        )
        fig_f.update_traces(
            texttemplate="R$ %{text:,.0f}",
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>R$ %{x:,.2f}<extra></extra>",
        )
        fig_f.update_layout(
            title="Top fornecedores (valor no filtro — vencimento)",
            yaxis=dict(categoryorder="total ascending"),
        )
        _layout_plotly_base(fig_f)
        st.plotly_chart(fig_f, width="stretch")
    else:
        st.info("Sem dados de fornecedor para o período.")

with g4:
    if not df_top_m.empty:
        fig_m = px.bar(
            df_top_m,
            x="valor_parcela",
            y="marca",
            orientation="h",
            text="valor_parcela",
            labels={"valor_parcela": "Valor (R$)", "marca": "Marca"},
            color_discrete_sequence=[COR_VENCIMENTO],
        )
        fig_m.update_traces(
            texttemplate="R$ %{text:,.0f}",
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>R$ %{x:,.2f}<extra></extra>",
        )
        fig_m.update_layout(
            title="Top marcas (valor no filtro — vencimento)",
            yaxis=dict(categoryorder="total ascending"),
        )
        _layout_plotly_base(fig_m)
        st.plotly_chart(fig_m, width="stretch")
    else:
        st.info("Sem dados de marca para o período.")

# Participação por marca (pizza) — vencimento
df_marca_share = (
    df_filtrado.groupby("marca", as_index=False)["valor_parcela"]
    .sum()
    .dropna(subset=["marca"])
)
if not df_marca_share.empty:
    df_marca_share = df_marca_share.sort_values("valor_parcela", ascending=False)
    top_n = 8
    if len(df_marca_share) > top_n:
        outros = df_marca_share.iloc[top_n:]["valor_parcela"].sum()
        df_marca_share = pd.concat(
            [
                df_marca_share.head(top_n),
                pd.DataFrame([{"marca": "Outros", "valor_parcela": outros}]),
            ],
            ignore_index=True,
        )
    fig_pie = px.pie(
        df_marca_share,
        values="valor_parcela",
        names="marca",
        title="Participação do valor por marca (vencimento)",
        hole=0.42,
        color_discrete_sequence=px.colors.sequential.Blues_r,
    )
    fig_pie.update_traces(
        textposition="inside",
        textinfo="percent+label",
        hovertemplate="<b>%{label}</b><br>R$ %{value:,.2f}<br>%{percent}<extra></extra>",
    )
    _layout_plotly_base(fig_pie, altura=420)
    st.plotly_chart(fig_pie, width="stretch")

# =========================
# META x REALIZADO
# =========================
st.divider()
_secao_fin_header(
    "2 · Meta x Realizado — Fluxo de Caixa",
    "Comparativo mensal entre a **meta de fluxo de caixa** cadastrada e o **valor realizado** "
    "(soma das parcelas já quitadas no mês pela data de baixa). "
    "Cadastre metas na página **Meta Fluxo de Caixa**.",
    "#7c3aed",
    "rgba(245, 243, 255, 0.92)",
)


@st.cache_data(ttl=120, show_spinner=False)
def _carregar_metas_financeiro():
    return listar_metas_fluxo_caixa()


_metas_raw = _carregar_metas_financeiro()

if not _metas_raw:
    st.info(
        "Nenhuma meta de fluxo de caixa cadastrada. "
        "Acesse a página **Meta Fluxo de Caixa** no menu lateral para cadastrar."
    )
else:
    df_metas = pd.DataFrame(_metas_raw)
    df_metas["ano"] = df_metas["ano"].astype(int)
    df_metas["mes"] = df_metas["mes"].astype(int)
    df_metas["valor"] = pd.to_numeric(df_metas["valor"], errors="coerce").fillna(0)
    df_metas["mes_ano_key"] = df_metas.apply(
        lambda r: f"{int(r['ano'])}-{int(r['mes']):02d}", axis=1
    )

    df_todas = df.copy()
    df_todas["mes_ano_key"] = df_todas["data_pagamento"].dt.strftime("%Y-%m")
    realizado_mes = (
        df_todas.dropna(subset=["mes_ano_key"])
        .groupby("mes_ano_key", as_index=False)["valor_parcela"]
        .sum()
        .rename(columns={"valor_parcela": "realizado"})
    )

    df_comp = df_metas[["mes_ano_key", "ano", "mes", "valor"]].rename(
        columns={"valor": "meta"}
    )
    df_comp = df_comp.merge(realizado_mes, on="mes_ano_key", how="left")
    df_comp["realizado"] = df_comp["realizado"].fillna(0)
    df_comp["saldo"] = df_comp["meta"] - df_comp["realizado"]
    df_comp = df_comp.sort_values(["ano", "mes"])
    df_comp["mes_ano_label"] = df_comp.apply(
        lambda r: f"{int(r['mes']):02d}/{int(r['ano'])}", axis=1
    )

    fig_comp = px.bar(
        df_comp.melt(
            id_vars=["mes_ano_label"],
            value_vars=["meta", "realizado"],
            var_name="Tipo",
            value_name="Valor",
        ),
        x="mes_ano_label",
        y="Valor",
        color="Tipo",
        barmode="group",
        text="Valor",
        labels={"mes_ano_label": "Mês/Ano", "Valor": "Valor (R$)"},
        color_discrete_map={"meta": "#7c3aed", "realizado": "#059669"},
    )
    fig_comp.update_traces(
        texttemplate="R$ %{text:,.0f}",
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>%{data.name}: R$ %{y:,.2f}<extra></extra>",
    )
    fig_comp.update_layout(
        title="Meta x Realizado por mês",
        legend_title_text="",
        xaxis_title="",
        yaxis_title="Valor (R$)",
    )
    _layout_plotly_base(fig_comp, altura=420)
    st.plotly_chart(fig_comp, width="stretch")

    rows_tabela = []
    for _, r in df_comp.iterrows():
        saldo = r["saldo"]
        if saldo >= 0:
            cor = "green"
            saldo_fmt = formatar_moeda_br(saldo)
        else:
            cor = "red"
            saldo_fmt = f"- {formatar_moeda_br(abs(saldo))}"
        rows_tabela.append({
            "Mês/Ano": r["mes_ano_label"],
            "Meta Fluxo": formatar_moeda_br(r["meta"]),
            "Valor Realizado": formatar_moeda_br(r["realizado"]),
            "_saldo_fmt": saldo_fmt,
            "_saldo_cor": cor,
        })

    df_tabela = pd.DataFrame(rows_tabela)

    html_rows = ""
    for _, row in df_tabela.iterrows():
        cor = row["_saldo_cor"]
        html_rows += (
            f"<tr>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;'>{row['Mês/Ano']}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right;'>{row['Meta Fluxo']}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right;'>{row['Valor Realizado']}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #e2e8f0;text-align:right;"
            f"color:{cor};font-weight:700;'>{row['_saldo_fmt']}</td>"
            f"</tr>"
        )

    st.markdown(
        f"""
        <table style="width:100%;border-collapse:collapse;font-size:0.95rem;margin-top:0.5rem;">
            <thead>
                <tr style="background:#f8fafc;">
                    <th style="padding:10px 12px;text-align:left;border-bottom:2px solid #cbd5e1;">Mês/Ano</th>
                    <th style="padding:10px 12px;text-align:right;border-bottom:2px solid #cbd5e1;">Meta Fluxo</th>
                    <th style="padding:10px 12px;text-align:right;border-bottom:2px solid #cbd5e1;">Valor Realizado</th>
                    <th style="padding:10px 12px;text-align:right;border-bottom:2px solid #cbd5e1;">Saldo</th>
                </tr>
            </thead>
            <tbody>
                {html_rows}
            </tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )

# =========================
# TABELA DETALHADA
# =========================
st.divider()
_secao_fin_header(
    "3 · Detalhamento consolidado",
    "Cada linha mostra o **vencimento** para conferência consolidada.",
    "#64748b",
    "rgba(248, 250, 252, 0.95)",
)
st.subheader("📋 Tabela — fornecedor, marca e valores")

df_exibir = df_filtrado[
    [
        "pedido_id",
        "numero_parcela",
        "data_pagamento",
        "data_quitacao",
        "fornecedor",
        "marca",
        "valor_parcela",
        "total_valor",
        "grupo",
        "pago",
    ]
].copy()

df_exibir["Data vencimento"] = df_exibir["data_pagamento"].dt.strftime("%d/%m/%Y")


df_exibir["valor_parcela_fmt"] = df_exibir["valor_parcela"].apply(formatar_moeda_br)
df_exibir["total_valor_fmt"] = df_exibir["total_valor"].apply(formatar_moeda_br)

df_exibir = df_exibir.rename(
    columns={
        "pedido_id": "Pedido",
        "numero_parcela": "Parcela",
        "fornecedor": "Fornecedor",
        "marca": "Marca",
        "valor_parcela_fmt": "Valor da parcela",
        "total_valor_fmt": "Valor total do pedido",
        "grupo": "Grupo",
    }
)
df_exibir = df_exibir.drop(
    columns=[
        "data_pagamento",
        "data_quitacao",
        "valor_parcela",
        "total_valor",
        "pago",
    ]
)

df_exibir = df_exibir[
    [
        "Pedido",
        "Parcela",
        "Data vencimento",
        "Fornecedor",
        "Marca",
        "Grupo",
        "Valor da parcela",
        "Valor total do pedido",
    ]
]

st.dataframe(
    df_exibir,
    width="stretch",
    hide_index=True,
    column_config={
        "Data vencimento": st.column_config.TextColumn("Data vencimento", width="small"),
        "Fornecedor": st.column_config.TextColumn("Fornecedor", width="large"),
        "Marca": st.column_config.TextColumn("Marca", width="medium"),
        "Valor da parcela": st.column_config.TextColumn("Valor da parcela", width="small"),
        "Valor total do pedido": st.column_config.TextColumn(
            "Valor total do pedido", width="small"
        ),
    },
)

# =========================
# EXPORTAÇÃO
# =========================
def exportar_excel_financeiro(df_export):
    import io

    output = io.BytesIO()

    df_excel = df_export.copy()
    d_v = pd.to_datetime(df_excel["data_pagamento"], errors="coerce")
    if "data_quitacao" not in df_excel.columns:
        df_excel["data_quitacao"] = pd.NaT
    d_q = pd.to_datetime(df_excel["data_quitacao"], errors="coerce")
    pago_b = df_excel["pago"].fillna(False).astype(bool)
    d_pag = d_q.copy()
    usar_venc = pago_b & d_q.isna() & d_v.notna()
    d_pag.loc[usar_venc] = d_v.loc[usar_venc]

    df_excel["data_pagamento"] = d_v.apply(
        lambda x: x.strftime("%d/%m/%Y") if pd.notna(x) else ""
    )
    df_excel["data_quitacao"] = d_pag.apply(
        lambda x: x.strftime("%d/%m/%Y") if pd.notna(x) else ""
    )
    if "pago" in df_excel.columns:
        df_excel["pago"] = df_excel["pago"].map(lambda x: "Sim" if bool(x) else "Não")

    colunas_pt = {
        "pedido_id": "Pedido",
        "numero_parcela": "Parcela",
        "data_pagamento": "Data vencimento",
        "data_quitacao": "Data pagamento",
        "fornecedor": "Fornecedor",
        "marca": "Marca",
        "valor_parcela": "Valor da parcela",
        "total_valor": "Valor total do pedido",
        "grupo": "Grupo",
        "pago": "Pago",
    }
    df_excel = df_excel.rename(columns=colunas_pt)

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_excel.to_excel(writer, index=False, sheet_name="Financeiro")

        workbook = writer.book
        worksheet = writer.sheets["Financeiro"]

        formato_moeda = workbook.add_format({"num_format": 'R$ #,##0.00'})

        worksheet.set_column("A:A", 10)
        worksheet.set_column("B:B", 10)
        worksheet.set_column("C:C", 14)
        worksheet.set_column("D:D", 14)
        worksheet.set_column("E:E", 28)
        worksheet.set_column("F:F", 22)
        worksheet.set_column("G:G", 14)
        worksheet.set_column("H:H", 18, formato_moeda)
        worksheet.set_column("I:I", 22, formato_moeda)
        worksheet.set_column("J:J", 10)

    return output.getvalue()

df_exportar = df_filtrado[
    [
        "pedido_id",
        "numero_parcela",
        "data_pagamento",
        "data_quitacao",
        "fornecedor",
        "marca",
        "valor_parcela",
        "total_valor",
        "grupo",
        "pago",
    ]
].copy()

excel_file = exportar_excel_financeiro(df_exportar)

st.divider()
st.subheader("📥 Exportação")
st.download_button(
    label="📥 Exportar Excel Financeiro",
    data=excel_file,
    file_name="dashboard_financeiro.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)