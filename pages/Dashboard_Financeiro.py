import calendar
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
from dateutil.relativedelta import relativedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from services.supabase_client import (
    supabase,
    atualizar_parcela_pago,
    data_baixa_hoje_iso,
    fetch_parcelas_para_financeiro,
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
ano_sel = col4.multiselect("Ano", sorted(df["data_pagamento"].dt.year.dropna().unique()))
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

# --- Pagamento efetivo (baixa) ---
st.divider()
_secao_fin_header(
    "2 · Visão por data de pagamento (efetivo)",
    "Somente parcelas **já quitadas**, pela data em que foram baixadas (saída real de caixa). "
    "O período abaixo é independente dos filtros Ano/Mês de vencimento. Cor verde nesta seção.",
    COR_PAGAMENTO,
    "rgba(236, 253, 245, 0.92)",
)

hoje_br = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
def_ini, def_fim = _primeiro_ultimo_dia_mes(hoje_br)
if "fin_evol_d_ini" not in st.session_state:
    st.session_state.fin_evol_d_ini = def_ini
    st.session_state.fin_evol_d_fim = def_fim
if "fin_evol_atalho" not in st.session_state:
    st.session_state.fin_evol_atalho = "Mês atual"

st.selectbox(
    "Atalho — período pela data de baixa",
    options=ATALHOS_PERIODO_BAIXA_FIN,
    key="fin_evol_atalho",
    on_change=_aplicar_atalho_baixa_fin_callback,
    help="Somente parcelas quitadas; filtra pela data da baixa (data_quitacao).",
)
dc1, dc2 = st.columns(2)
with dc1:
    d_ini = st.date_input(
        "De (data de baixa)",
        key="fin_evol_d_ini",
        format="DD/MM/YYYY",
        on_change=_marcar_periodo_baixa_personalizado_callback,
    )
with dc2:
    d_fim = st.date_input(
        "Até (data de baixa)",
        key="fin_evol_d_fim",
        format="DD/MM/YYYY",
        on_change=_marcar_periodo_baixa_personalizado_callback,
    )
if d_ini > d_fim:
    d_ini, d_fim = d_fim, d_ini

df_efet = df_filtrado[df_filtrado["pago"] == True].copy()
df_efet["data_baixa"] = pd.to_datetime(df_efet["data_quitacao"], errors="coerce")
df_efet = df_efet.dropna(subset=["data_baixa"])
dnorm = df_efet["data_baixa"].dt.normalize().dt.date
df_efet = df_efet.loc[(dnorm >= d_ini) & (dnorm <= d_fim)]

if df_efet.empty:
    fig_por_data = go.Figure()
    fig_por_data.add_annotation(
        text=(
            "Nenhuma parcela paga com data de baixa neste período. "
            "Ajuste as datas acima ou use a baixa de parcelas (coluna data_quitacao no Supabase)."
        ),
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=13, color="#475569"),
    )
    fig_por_data.update_layout(
        title="Evolução por data de pagamento (efetivo)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    _layout_plotly_base(fig_por_data, altura=320)
else:
    dmin = df_efet["data_baixa"].min()
    dmax = df_efet["data_baixa"].max()
    span_days = max((dmax - dmin).days + 1, 1)
    db = pd.to_datetime(df_efet["data_baixa"])
    if span_days > 90:
        df_efet["_bucket"] = db.dt.to_period("W-MON").dt.to_timestamp()
        titulo_periodo = "Evolução dos pagamentos efetivos por semana"
        eixo_x = "Semana (início na segunda-feira)"
    else:
        df_efet["_bucket"] = db.dt.strftime("%Y-%m-%d")

    df_por_data = (
        df_efet.groupby("_bucket", as_index=False)
        .agg(
            valor=("valor_parcela", "sum"),
            qtd_parcelas=("valor_parcela", "count"),
        )
        .sort_values("_bucket")
    )
    df_por_data["periodo"] = pd.to_datetime(df_por_data["_bucket"])
    df_por_data = df_por_data.drop(columns=["_bucket"])

    if span_days <= 90:
        titulo_periodo = "Evolução dos pagamentos efetivos por dia"
        eixo_x = "Data do pagamento (baixa)"

    fig_por_data = go.Figure(
        go.Scatter(
            x=df_por_data["periodo"],
            y=df_por_data["valor"],
            mode="lines+markers",
            line=dict(color=COR_PAGAMENTO, width=2.75),
            marker=dict(size=10, color=COR_PAGAMENTO, line=dict(width=1, color="white")),
            name="Valor pago",
            hovertemplate=(
                "<b>%{x|%d/%m/%Y}</b><br>"
                "<b>Total pago:</b> R$ %{y:,.2f}<br>"
                "<b>Parcelas quitadas:</b> %{customdata[0]:.0f}<extra></extra>"
            ),
            customdata=df_por_data[["qtd_parcelas"]].values,
        )
    )
    fig_por_data.update_layout(
        title=titulo_periodo,
        xaxis_title=eixo_x,
        yaxis_title="Valor pago (R$)",
        showlegend=False,
    )
    _layout_plotly_base(fig_por_data)
    fig_por_data.update_yaxes(rangemode="tozero", gridcolor="rgba(148,163,184,0.25)")
    fig_por_data.update_xaxes(
        type="date",
        tickmode="array",
        tickvals=df_por_data["periodo"].tolist(),
        tickformat="%d/%m/%Y",
        tickangle=-35,
        gridcolor="rgba(148,163,184,0.2)",
    )

st.plotly_chart(fig_por_data, width="stretch")

st.markdown(
    f"<p style='font-size:0.9rem;color:#475569;margin:0.75rem 0 0.35rem 0;'>"
    f"<strong style='color:{COR_PAGAMENTO};'>Registrar pagamento:</strong> "
    "ao salvar, grava a data de baixa e a parcela passa a contar na visão acima.</p>",
    unsafe_allow_html=True,
)

# =========================
# BAIXA DE PARCELAS (PAGO)
# =========================
st.subheader("💳 Baixa de parcelas")

if not TEM_COLUNA_PAGO:
    st.info(
        "A coluna **pago** ainda não existe em `pedido_parcelas`. "
        "Execute o script em `supabase/migrations/001_add_status_columns.sql` no Supabase "
        "para habilitar a baixa de parcelas aqui. O restante do dashboard continua funcionando."
    )
elif "parcela_id" not in df_filtrado.columns or df_filtrado["parcela_id"].isna().all():
    st.warning("Não foi possível obter o ID das parcelas para baixa.")
else:
    st.caption(
        "Somente parcelas **ainda não pagas** (pendentes). Marque **Pago** e clique em **Salvar**. "
        "Boletos já quitados somem desta lista e continuam no detalhamento abaixo."
    )

    df_baixa = df_filtrado[
        [
            "parcela_id",
            "pedido_id",
            "numero_parcela",
            "data_pagamento",
            "fornecedor",
            "marca",
            "valor_parcela",
            "pago",
        ]
    ].copy()
    df_baixa = df_baixa.dropna(subset=["parcela_id"])
    # Baixa: só pendentes — parcelas já pagas não aparecem aqui
    df_baixa = df_baixa[~df_baixa["pago"].fillna(False).astype(bool)]
    df_baixa = df_baixa.sort_values(
        ["data_pagamento", "pedido_id", "numero_parcela"],
        na_position="last",
    )

    if df_baixa.empty:
        st.info(
            "Nenhuma parcela **pendente** no filtro atual (todas já pagas ou nenhuma parcela)."
        )
    else:
        df_edit = st.data_editor(
            df_baixa,
            column_config={
                "parcela_id": st.column_config.NumberColumn(
                    "ID parcela", disabled=True, format="%d"
                ),
                "pedido_id": st.column_config.NumberColumn("Pedido", disabled=True, format="%d"),
                "numero_parcela": st.column_config.NumberColumn(
                    "Parcela", disabled=True, format="%d"
                ),
                "data_pagamento": st.column_config.DateColumn(
                    "Vencimento", disabled=True, format="DD/MM/YYYY"
                ),
                "fornecedor": st.column_config.TextColumn("Fornecedor", disabled=True),
                "marca": st.column_config.TextColumn("Marca", disabled=True),
                "valor_parcela": st.column_config.NumberColumn(
                    "Valor (R$)", disabled=True, format="%.2f"
                ),
                "pago": st.column_config.CheckboxColumn("Pago"),
            },
            hide_index=True,
            width="stretch",
            key="editor_baixa_parcelas",
            num_rows="fixed",
        )

        if st.button("💾 Salvar status de pagamento", key="salvar_baixa"):
            try:
                hoje_baixa = data_baixa_hoje_iso()
                alteradas = 0
                for _, r in df_edit.iterrows():
                    orig = df_baixa.loc[
                        df_baixa["parcela_id"] == r["parcela_id"], "pago"
                    ].iloc[0]
                    orig_b = bool(orig) if pd.notna(orig) else False
                    novo_b = bool(r["pago"]) if pd.notna(r["pago"]) else False
                    if orig_b != novo_b:
                        atualizar_parcela_pago(
                            int(r["parcela_id"]),
                            novo_b,
                            data_quitacao=hoje_baixa if novo_b else None,
                        )
                        alteradas += 1
                carregar_financeiro.clear()
                if alteradas:
                    st.success(f"Atualizado: {alteradas} parcela(s).")
                else:
                    st.info("Nenhuma alteração de status.")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar (migração SQL e permissões RLS): {e}")

# =========================
# TABELA DETALHADA
# =========================
st.divider()
_secao_fin_header(
    "3 · Detalhamento consolidado",
    "Cada linha mostra **vencimento** e **pagamento** (quando houver) para conferência cruzada.",
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


def _fmt_data_pagamento_exibicao(row):
    """Data da baixa; se pago sem data gravada, usa vencimento como referência."""
    if pd.notna(row["data_quitacao"]):
        return pd.Timestamp(row["data_quitacao"]).strftime("%d/%m/%Y")
    if bool(row["pago"]) and pd.notna(row["data_pagamento"]):
        return pd.Timestamp(row["data_pagamento"]).strftime("%d/%m/%Y")
    return "—"


df_exibir["Data pagamento"] = df_exibir.apply(_fmt_data_pagamento_exibicao, axis=1)
df_exibir["valor_parcela_fmt"] = df_exibir["valor_parcela"].apply(formatar_moeda_br)
df_exibir["total_valor_fmt"] = df_exibir["total_valor"].apply(formatar_moeda_br)
df_exibir["Situação"] = df_exibir["pago"].map(lambda x: "Pago" if x else "Pendente")

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
        "Data pagamento",
        "Fornecedor",
        "Marca",
        "Grupo",
        "Valor da parcela",
        "Valor total do pedido",
        "Situação",
    ]
]

st.dataframe(
    df_exibir,
    width="stretch",
    hide_index=True,
    column_config={
        "Data vencimento": st.column_config.TextColumn("Data vencimento", width="small"),
        "Data pagamento": st.column_config.TextColumn("Data pagamento", width="small"),
        "Fornecedor": st.column_config.TextColumn("Fornecedor", width="large"),
        "Marca": st.column_config.TextColumn("Marca", width="medium"),
        "Valor da parcela": st.column_config.TextColumn("Valor da parcela", width="small"),
        "Valor total do pedido": st.column_config.TextColumn(
            "Valor total do pedido", width="small"
        ),
        "Situação": st.column_config.TextColumn("Situação", width="small"),
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