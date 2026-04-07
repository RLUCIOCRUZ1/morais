import streamlit as st
import pandas as pd
from datetime import datetime
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from services.supabase_client import (
    inserir_pedido,
    inserir_itens,
    inserir_parcelas,
    listar_pedidos_resumo,
    buscar_pedido_completo,
    atualizar_pedido,
    deletar_itens_pedido,
    deletar_parcelas_pedido,
    excluir_pedido_completo,
)
from services.branding import show_sidebar_branding


GRUPOS = ["Feminino", "Masculino", "Infantil", "Esportivo", "Acessórios", "Vestuário"]


def _infer_periodicidade(parcelas):
    if not parcelas or len(parcelas) < 2:
        return "Mensal"
    d0 = pd.to_datetime(parcelas[0]["data_pagamento"])
    d1 = pd.to_datetime(parcelas[1]["data_pagamento"])
    diff = (d1 - d0).days
    if diff <= 2:
        return "Diária"
    if 5 <= diff <= 9:
        return "Semanal"
    if 25 <= diff <= 35:
        return "Mensal"
    if 300 <= diff <= 400:
        return "Anual"
    return "Mensal"


def _aplicar_pedido_na_sessao(ped_row, itens, parcelas):
    st.session_state.pedido_editando_id = ped_row["id"]
    st.session_state.fornecedor = (ped_row.get("fornecedor") or "").strip()
    st.session_state.marca = (ped_row.get("marca") or "").strip()
    g = ped_row.get("grupo") or "Feminino"
    st.session_state.grupo_pedido = g if g in GRUPOS else "Feminino"
    st.session_state.data_chegada = pd.to_datetime(ped_row["data_chegada"]).date()
    st.session_state.itens = [
        {
            "id": x["id"],
            "referencia": (x.get("referencia") or "").strip(),
            "quantidade": int(x.get("quantidade", 1)),
            "custo": float(x.get("custo_unitario", 0)),
        }
        for x in itens
    ]
    st.session_state.itens_excluidos = []
    np = len(parcelas)
    st.session_state.qtd_parcelas_inp = max(1, np)
    if parcelas:
        d0 = pd.to_datetime(parcelas[0]["data_pagamento"])
        st.session_state.data_inicial = d0.date()
    if np > 1:
        st.session_state.periodicidade_sel = _infer_periodicidade(parcelas)
    st.session_state.form_key += 1


def _limpar_estado_formulario_cadastro():
    st.session_state.itens = [
        {"id": None, "referencia": "", "quantidade": 1, "custo": 0.0}
    ]
    st.session_state.itens_excluidos = []
    st.session_state.pedido_editando_id = None
    for key in [
        "fornecedor",
        "marca",
        "data_chegada",
        "data_inicial",
        "grupo_pedido",
        "qtd_parcelas_inp",
        "periodicidade_sel",
    ]:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state.form_key += 1
    fk = st.session_state.form_key
    for i in range(len(st.session_state.itens)):
        for campo in ["ref", "qtd", "custo"]:
            k = f"{campo}_{i}_{fk}"
            if k in st.session_state:
                del st.session_state[k]


st.set_page_config(page_title="Cadastro Pedido", layout="wide")

show_sidebar_branding()

st.title("📦 Cadastro de Pedido")

if "pedido_editando_id" not in st.session_state:
    st.session_state.pedido_editando_id = None

modo = st.radio(
    "Modo",
    ["Novo pedido", "Editar pedido existente"],
    horizontal=True,
    key="modo_cadastro",
)

_prev_m = st.session_state.get("_prev_modo_cadastro")
if _prev_m == "Editar pedido existente" and modo == "Novo pedido":
    st.session_state.pedido_editando_id = None
st.session_state._prev_modo_cadastro = modo

if modo == "Editar pedido existente":
    _lista = listar_pedidos_resumo()
    if not _lista:
        st.warning("Nenhum pedido cadastrado para editar.")
    else:
        _labels = {
            f"#{r['id']} — {r.get('fornecedor', '')} ({r.get('marca', '')})": r["id"]
            for r in _lista
        }
        escolha = st.selectbox("Selecione o pedido", list(_labels.keys()), key="sel_pedido_editar")
        c_load, c_cancel = st.columns(2)
        if c_load.button("📥 Carregar pedido"):
            _pid = _labels[escolha]
            ped_row, itens, parcelas = buscar_pedido_completo(_pid)
            if ped_row is None:
                st.error("Pedido não encontrado.")
            else:
                _aplicar_pedido_na_sessao(ped_row, itens, parcelas)
                st.rerun()
        if c_cancel.button("Encerrar edição"):
            if st.session_state.pedido_editando_id:
                st.session_state.pedido_editando_id = None
                st.rerun()

        with st.expander("🗑 Excluir pedido sem carregar no formulário", expanded=False):
            st.caption(
                "Remove o pedido, itens e parcelas no banco. "
                "Confirme abaixo antes de clicar em excluir."
            )
            sel_ex = st.selectbox(
                "Pedido a excluir",
                list(_labels.keys()),
                key="sel_excluir_pedido_lista",
            )
            chk_ex_lista = st.checkbox(
                "Confirmo exclusão permanente",
                key="chk_excluir_pedido_lista",
            )
            if st.button(
                "Excluir pedido selecionado",
                type="primary",
                key="btn_excluir_pedido_lista",
                disabled=not chk_ex_lista,
            ):
                if chk_ex_lista:
                    try:
                        pid_x = _labels[sel_ex]
                        excluir_pedido_completo(pid_x)
                        st.session_state.sucesso = f"Pedido {pid_x} excluído."
                        if st.session_state.pedido_editando_id == pid_x:
                            _limpar_estado_formulario_cadastro()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao excluir (RLS ou vínculos no banco): {e}")

if st.session_state.pedido_editando_id:
    st.warning(
        f"**Editando pedido nº {st.session_state.pedido_editando_id}.** "
        "Ao salvar, itens e parcelas serão substituídos; "
        "marcações de **parcela paga** podem ser perdidas se você alterar parcelamento."
    )
    with st.expander("🗑 Excluir este pedido", expanded=False):
        st.caption(
            "Apaga no banco o pedido em edição, todas as referências (itens) e parcelas. "
            "Não é possível desfazer."
        )
        chk_del_atual = st.checkbox(
            "Confirmo que quero apagar permanentemente",
            key="chk_excluir_pedido_atual",
        )
        if st.button(
            "Excluir pedido permanentemente",
            type="primary",
            key="btn_excluir_pedido_atual",
            disabled=not chk_del_atual,
        ):
            if chk_del_atual:
                try:
                    pid_del = st.session_state.pedido_editando_id
                    excluir_pedido_completo(pid_del)
                    st.session_state.sucesso = f"Pedido {pid_del} excluído."
                    _limpar_estado_formulario_cadastro()
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao excluir (RLS ou vínculos no banco): {e}")

if "fornecedor" not in st.session_state:
    st.session_state.fornecedor = ""

if "marca" not in st.session_state:
    st.session_state.marca = ""

if "form_key" not in st.session_state:
    st.session_state.form_key = 0    

if "data_chegada" not in st.session_state:
    st.session_state.data_chegada = datetime.today()

if "data_inicial" not in st.session_state:
    st.session_state.data_inicial = datetime.today()

if "sucesso" in st.session_state:
    st.success(st.session_state.sucesso)
    del st.session_state.sucesso





# =========================
# CABEÇALHO DO PEDIDO
# =========================

st.subheader("📌 Informações Gerais")

col1, col2, col3, col4 = st.columns(4)

fornecedor = col1.text_input("Fornecedor", key="fornecedor")
if "grupo_pedido" not in st.session_state:
    st.session_state.grupo_pedido = GRUPOS[0]
grupo = col2.selectbox("Grupo de Produto", GRUPOS, key="grupo_pedido")
marca = col3.text_input("Marca", key="marca")
data_chegada = col4.date_input("Data de Chegada", key="data_chegada")

data_chegada_br = data_chegada.strftime("%d/%m/%Y") if data_chegada else ""

# CSS limpo e controlado
col4.markdown(f"""
<style>
[data-testid="stDateInput"] {{
    position: relative;
}}

[data-testid="stDateInput"] input {{
    color: transparent !important;
}}

[data-testid="stDateInput"]::after {{
    content: "📅 {data_chegada_br}";
    position: absolute;
    left: 12px;
    top: 38px;
    font-size: 15px;
    color: #333;
    pointer-events: none;
}}
</style>
""", unsafe_allow_html=True)

# =========================
# REFERÊNCIAS DINÂMICAS
# =========================

if "itens" not in st.session_state:
    st.session_state.itens = [
        {"id": None, "referencia": "", "quantidade": 1, "custo": 0.0}
    ]

if "itens_excluidos" not in st.session_state:
    st.session_state.itens_excluidos = []

st.markdown("---")
st.subheader("📦 Itens do Pedido")

def remover_item(index):
    item = st.session_state.itens[index]

    # se vier do banco no futuro
    if item.get("id"):
        st.session_state.itens_excluidos.append(item["id"])

    st.session_state.itens.pop(index)

# botão adicionar
if st.button("➕ Adicionar Referência"):
    st.session_state.itens.append(
        {"id": None, "referencia": "", "quantidade": 1, "custo": 0.0}
    )



total_geral = 0
total_qtd = 0

for i, item in enumerate(st.session_state.itens):

    col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])

    referencia = col1.text_input(
        f"Referência {i+1}",
        value=item["referencia"],
        key=f"ref_{i}_{st.session_state.form_key}"
    )

    quantidade = col2.number_input(
        "Qtd",
        min_value=1,
        value=int(item.get("quantidade", 1)),
        key=f"qtd_{i}_{st.session_state.form_key}"
    )

    custo = col3.number_input(
        "Custo (R$)",
        min_value=0.0,
        format="%.2f",
        value=item["custo"],
        key=f"custo_{i}_{st.session_state.form_key}"
    )

    total_item = quantidade * custo

    col4.write(f"💰 R$ {total_item:,.2f}")

    # BOTÃO REMOVER
    if len(st.session_state.itens) > 1:
        if col5.button("🗑", key=f"remover_{i}_{st.session_state.form_key}"):

            remover_item(i)

            st.session_state.form_key += 1
            st.rerun()

    # atualizar session
    st.session_state.itens[i] = {
        "id": item.get("id"),
        "referencia": referencia,
        "quantidade": quantidade,
        "custo": custo
    }

    total_geral += total_item
    total_qtd += quantidade

# =========================
# TOTALIZADORES
# =========================

st.markdown("---")
col1, col2 = st.columns(2)

col1.metric("📦 Total Quantidade", total_qtd)
col2.metric("💰 Total do Pedido", f"R$ {total_geral:,.2f}")

# =========================
# PARCELAMENTO
# =========================

st.markdown("---")
st.subheader("📅 Parcelamento")

st.session_state.setdefault("qtd_parcelas_inp", 1)
qtd_parcelas = st.number_input(
    "Quantidade de parcelas",
    min_value=1,
    key="qtd_parcelas_inp",
)

if qtd_parcelas == 1:
    periodicidade = "Única"
    st.info("Periodicidade: Única")
else:
    if "periodicidade_sel" not in st.session_state:
        st.session_state.periodicidade_sel = "Mensal"
    periodicidade = st.selectbox(
        "Periodicidade",
        ["Mensal", "Semanal", "Diária", "Anual"],
        key="periodicidade_sel",
    )

data_inicial = st.date_input("Data inicial do pagamento", key="data_inicial")

data_inicial_br = data_inicial.strftime("%d/%m/%Y") if data_inicial else ""

st.markdown(f"""
<style>
[data-testid="stDateInput"] {{
    position: relative;
}}

[data-testid="stDateInput"] input {{
    color: transparent !important;
}}

[data-testid="stDateInput"]::after {{
    content: "📅 {data_inicial_br}";
    position: absolute;
    left: 12px;
    top: 38px;
    font-size: 15px;
    color: #333;
    pointer-events: none;
}}
</style>
""", unsafe_allow_html=True)


# =========================
# BOTÃO SALVAR
# =========================

st.markdown("---")

_btn_label = (
    "💾 Atualizar pedido"
    if st.session_state.pedido_editando_id
    else "💾 Salvar Pedido"
)

if st.button(_btn_label, width="stretch"):

    if not fornecedor:
        st.warning("Informe o fornecedor")
        st.stop()

    if total_qtd == 0:
        st.warning("Adicione pelo menos um item")
        st.stop()

    try:
        pedido_data = {
            "fornecedor": fornecedor,
            "grupo": grupo,
            "marca": marca,
            "data_chegada": data_chegada.strftime("%Y-%m-%d"),
            "total_quantidade": total_qtd,
            "total_valor": total_geral,
        }

        itens_insert = []
        for item in st.session_state.itens:
            total_item = item["quantidade"] * item["custo"]
            itens_insert.append(
                {
                    "referencia": item["referencia"],
                    "quantidade": item["quantidade"],
                    "custo_unitario": item["custo"],
                    "custo_total": total_item,
                }
            )

        parcelas_insert = []
        valor_base = round(total_geral / qtd_parcelas, 2)
        for i in range(qtd_parcelas):
            if i == qtd_parcelas - 1:
                valor_parcela = round(
                    total_geral - (valor_base * (qtd_parcelas - 1)), 2
                )
            else:
                valor_parcela = valor_base

            if periodicidade == "Mensal":
                data_pagamento = data_inicial + relativedelta(months=i)
            elif periodicidade == "Semanal":
                data_pagamento = data_inicial + timedelta(days=7 * i)
            elif periodicidade == "Diária":
                data_pagamento = data_inicial + timedelta(days=i)
            elif periodicidade == "Anual":
                data_pagamento = data_inicial + relativedelta(years=i)
            else:
                data_pagamento = data_inicial

            parcelas_insert.append(
                {
                    "numero_parcela": i + 1,
                    "valor_parcela": valor_parcela,
                    "data_pagamento": data_pagamento.strftime("%Y-%m-%d"),
                }
            )

        if st.session_state.pedido_editando_id:
            pedido_id = st.session_state.pedido_editando_id
            atualizar_pedido(pedido_id, pedido_data)
            deletar_itens_pedido(pedido_id)
            for row in itens_insert:
                row["pedido_id"] = pedido_id
            inserir_itens(itens_insert)
            deletar_parcelas_pedido(pedido_id)
            for row in parcelas_insert:
                row["pedido_id"] = pedido_id
            inserir_parcelas(parcelas_insert)
            st.session_state.sucesso = f"Pedido {pedido_id} atualizado com sucesso!"
            st.session_state.pedido_editando_id = None
        else:
            pedido_insert = inserir_pedido(pedido_data)
            pedido_id = pedido_insert[0]["id"]
            for row in itens_insert:
                row["pedido_id"] = pedido_id
            inserir_itens(itens_insert)
            for row in parcelas_insert:
                row["pedido_id"] = pedido_id
            inserir_parcelas(parcelas_insert)
            st.session_state.sucesso = f"Pedido salvo com sucesso! ID: {pedido_id}"

        _limpar_estado_formulario_cadastro()
        st.rerun()

    except Exception as e:
        st.error(f"Erro ao salvar: {e}")