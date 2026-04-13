import json
import os
import streamlit as st
import pandas as pd
from datetime import date, datetime
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from services.supabase_client import (
    inserir_pedido,
    inserir_itens,
    inserir_parcelas,
    inserir_condicao_pagamento,
    excluir_condicao_pagamento,
    listar_condicoes_pagamento,
    listar_pedidos_resumo,
    buscar_pedido_completo,
    atualizar_pedido,
    deletar_itens_pedido,
    deletar_parcelas_pedido,
    excluir_pedido_completo,
)
from services.branding import show_sidebar_branding


GRUPOS = ["Feminino", "Masculino", "Infantil", "Esportivo", "Acessórios", "Vestuário"]

_SQL_CONDICOES_PAGAMENTO_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "supabase",
        "migrations",
        "005_condicoes_pagamento.sql",
    )
)


def _texto_sql_condicoes_pagamento():
    try:
        with open(_SQL_CONDICOES_PAGAMENTO_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _erro_tabela_condicoes_ausente(msg: str) -> bool:
    m = (msg or "").lower()
    return "pgrst205" in m or "condicoes_pagamento" in m or "schema cache" in m


def _ui_instrucoes_sql_condicoes_pagamento():
    sql = _texto_sql_condicoes_pagamento()
    st.markdown(
        "1. Abra o [Supabase](https://supabase.com/dashboard) → seu projeto → **SQL Editor**.  \n"
        "2. Cole o script abaixo e clique em **Run**.  \n"
        "3. Recarregue esta página (e espere alguns segundos se o erro persistir — o PostgREST "
        "atualiza o cache do schema)."
    )
    if sql:
        st.code(sql, language="sql")
    else:
        st.warning(
            f"Não foi possível ler o arquivo no projeto: `{_SQL_CONDICOES_PAGAMENTO_PATH}`. "
            "Abra manualmente `supabase/migrations/005_condicoes_pagamento.sql` e execute no SQL Editor."
        )


def _coerce_prazos_list(val):
    if val is None:
        return []
    if isinstance(val, list):
        return [int(x) for x in val]
    if isinstance(val, str):
        return [int(x) for x in json.loads(val)]
    return [int(x) for x in val]


def _inferir_prazos_dias_de_parcelas(data_chegada, parcelas):
    """Padrão mercado: cada prazo = dias corridos após a data de chegada (entrega)."""
    if not parcelas:
        return []
    d_ch = pd.to_datetime(data_chegada).date()
    sorted_p = sorted(parcelas, key=lambda x: int(x.get("numero_parcela", 0)))
    prazos = []
    for p in sorted_p:
        d_pay = pd.to_datetime(p["data_pagamento"]).date()
        prazos.append(max(0, (d_pay - d_ch).days))
    return prazos


def _datas_vencimento_por_prazos(data_chegada: date, prazos_dias: list) -> list:
    """Cada parcela: data de chegada + prazos[k] dias (padrão mercado)."""
    out = []
    for dias in prazos_dias:
        out.append(data_chegada + timedelta(days=int(dias)))
    return out


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
    st.session_state.cond_pg_modo = "dias"
    st.session_state.form_key += 1
    fk = st.session_state.form_key
    pr_inf = _inferir_prazos_dias_de_parcelas(ped_row["data_chegada"], parcelas)
    for i in range(max(st.session_state.qtd_parcelas_inp, 1)):
        st.session_state[f"prazo_parcela_{i}_{fk}"] = (
            pr_inf[i] if i < len(pr_inf) else (pr_inf[-1] if pr_inf else 30)
        )


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
        "cond_pg_modo",
        "sel_condicao_pg_id",
    ]:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state.cond_pg_modo = "dias"
    st.session_state.sel_condicao_pg_id = "__custom"
    st.session_state.form_key += 1
    fk = st.session_state.form_key
    for i in range(len(st.session_state.itens)):
        for campo in ["ref", "qtd", "custo"]:
            k = f"{campo}_{i}_{fk}"
            if k in st.session_state:
                del st.session_state[k]


st.set_page_config(page_title="Cadastro Pedido", layout="wide")

from services.auth import require_login

require_login()


@st.cache_data(ttl=120, show_spinner=False)
def _pedidos_resumo_cached():
    return listar_pedidos_resumo()


def _invalidar_cache_pedidos_resumo():
    _pedidos_resumo_cached.clear()


@st.cache_data(ttl=120, show_spinner=False)
def _condicoes_pagamento_cached():
    return listar_condicoes_pagamento()


def _invalidar_cache_condicoes_pagamento():
    _condicoes_pagamento_cached.clear()


def _aplicar_condicao_selecionada():
    sel = st.session_state.get("sel_condicao_pg_id")
    if not sel or sel == "__custom":
        return
    lista = _condicoes_pagamento_cached()
    row = next((x for x in lista if str(x.get("id")) == str(sel)), None)
    if not row:
        return
    prazos = _coerce_prazos_list(row.get("prazos_dias"))
    qtd = int(row.get("qtd_parcelas") or 0)
    if not prazos or qtd < 1 or len(prazos) != qtd:
        return
    st.session_state.qtd_parcelas_inp = qtd
    fk = st.session_state.form_key
    for i, p in enumerate(prazos):
        st.session_state[f"prazo_parcela_{i}_{fk}"] = int(p)


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
    _lista = _pedidos_resumo_cached()
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
                        _invalidar_cache_pedidos_resumo()
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
                    _invalidar_cache_pedidos_resumo()
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
data_chegada = col4.date_input(
    "Data de Chegada",
    key="data_chegada",
    format="DD/MM/YYYY",
)

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
st.session_state.setdefault("cond_pg_modo", "dias")
st.session_state.setdefault("sel_condicao_pg_id", "__custom")

qtd_parcelas = st.number_input(
    "Quantidade de parcelas",
    min_value=1,
    key="qtd_parcelas_inp",
)

st.radio(
    "Como definir as datas de vencimento?",
    options=["dias", "periodicidade"],
    format_func=lambda x: (
        "Prazos em dias (a partir da data de chegada)"
        if x == "dias"
        else "Periodicidade fixa (mensal, semanal, diária…)"
    ),
    key="cond_pg_modo",
    horizontal=True,
)

fk_par = st.session_state.form_key
modo_pg = st.session_state.cond_pg_modo

if modo_pg == "dias":
    st.caption(
        "**Padrão mercado:** cada parcela usa **dias corridos após a data de chegada** "
        "(entrega). Ex.: chegada 10/06, 2x com 75 e 105 → vencimentos 24/08 e 23/11 "
        "(sempre somando a partir da **mesma** data de chegada)."
    )
    lista_cp = _condicoes_pagamento_cached()
    if not lista_cp:
        st.warning(
            "Não há condições na lista (a tabela **condicoes_pagamento** pode ainda não existir "
            "no Supabase). Crie a tabela uma vez com o script abaixo."
        )
        with st.expander("📋 Copiar SQL — criar tabela `condicoes_pagamento`", expanded=True):
            _ui_instrucoes_sql_condicoes_pagamento()
    opt_ids = ["__custom"] + [str(c["id"]) for c in lista_cp]

    def _label_condicao(cid):
        if cid == "__custom":
            return "Personalizar (editar prazos abaixo)"
        for c in lista_cp:
            if str(c["id"]) == cid:
                pr = _coerce_prazos_list(c.get("prazos_dias"))
                s = "/".join(str(p) for p in pr)
                return f"{c.get('nome', '')} — {c.get('qtd_parcelas')}x ({s} d.)"
        return cid

    st.selectbox(
        "Condição de pagamento (lista salva)",
        options=opt_ids,
        format_func=_label_condicao,
        key="sel_condicao_pg_id",
        on_change=_aplicar_condicao_selecionada,
        help="Ao escolher uma opção, a quantidade de parcelas e os dias são preenchidos. "
        "Você pode gravar novas combinações na lista (expander abaixo).",
    )

    with st.expander("➕ Gravar / gerenciar condições na lista", expanded=False):
        st.caption(
            "Grava os **prazos atuais** do formulário (quantidade de parcelas + dias) "
            "para reutilizar em pedidos futuros."
        )
        nome_nova = st.text_input(
            "Nome da condição (ex.: Fornecedor X — 45/90)",
            key="nova_condicao_nome",
        )
        c1, c2 = st.columns(2)
        if c1.button("Gravar condição atual na lista", key="btn_gravar_condicao_pg"):
            fk_g = st.session_state.form_key
            nparc_g = int(st.session_state.get("qtd_parcelas_inp", 1))
            pr_g = [
                int(st.session_state.get(f"prazo_parcela_{i}_{fk_g}", 0))
                for i in range(nparc_g)
            ]
            if not nome_nova.strip():
                st.warning("Informe um nome para a condição.")
            else:
                try:
                    inserir_condicao_pagamento(nome_nova.strip(), nparc_g, pr_g)
                    _invalidar_cache_condicoes_pagamento()
                    st.session_state.sel_condicao_pg_id = "__custom"
                    st.success("Condição gravada. Ela aparecerá na lista acima.")
                    st.rerun()
                except Exception as e:
                    err_txt = str(e)
                    st.error(f"Não foi possível gravar: {err_txt}")
                    if _erro_tabela_condicoes_ausente(err_txt):
                        with st.expander(
                            "📋 Criar a tabela no Supabase (erro PGRST205 / tabela não encontrada)",
                            expanded=True,
                        ):
                            _ui_instrucoes_sql_condicoes_pagamento()
        if lista_cp and c2.button("Atualizar lista do banco", key="btn_refresh_cond_pg"):
            _invalidar_cache_condicoes_pagamento()
            st.rerun()
        if lista_cp:
            st.markdown("**Excluir uma condição**")
            op_del = st.selectbox(
                "Selecione para excluir",
                options=["—"] + [str(c["id"]) for c in lista_cp],
                format_func=lambda x: (
                    "—"
                    if x == "—"
                    else next(
                        f"{c['nome']} (id {c['id']})"
                        for c in lista_cp
                        if str(c["id"]) == x
                    )
                ),
                key="sel_excluir_condicao_pg",
            )
            if st.button("Excluir condição selecionada", key="btn_excluir_condicao_pg"):
                if op_del != "—":
                    try:
                        excluir_condicao_pagamento(int(op_del))
                        _invalidar_cache_condicoes_pagamento()
                        st.session_state.sel_condicao_pg_id = "__custom"
                        st.success("Condição removida.")
                        st.rerun()
                    except Exception as e:
                        err_txt = str(e)
                        st.error(f"Erro ao excluir: {err_txt}")
                        if _erro_tabela_condicoes_ausente(err_txt):
                            with st.expander("📋 Criar a tabela no Supabase", expanded=True):
                                _ui_instrucoes_sql_condicoes_pagamento()

    prazos_lidos = []
    for i in range(int(qtd_parcelas)):
        k_prazo = f"prazo_parcela_{i}_{fk_par}"
        if k_prazo not in st.session_state:
            st.session_state[k_prazo] = 30 * (i + 1) if int(qtd_parcelas) <= 3 else 30
        legenda = "dias corridos após a data de chegada (entrega)"
        prazos_lidos.append(
            st.number_input(
                f"Parcela {i + 1} — {legenda}",
                min_value=0,
                max_value=3650,
                step=1,
                key=k_prazo,
            )
        )
    datas_prev = _datas_vencimento_por_prazos(data_chegada, prazos_lidos)
    st.markdown("**Datas calculadas automaticamente**")
    entrega_txt = data_chegada.strftime("%d/%m/%Y")
    _rows = []
    for idx, (d, dias) in enumerate(zip(datas_prev, prazos_lidos), start=1):
        _rows.append(
            {
                "Parcela": idx,
                "Dias após entrega": dias,
                "Data entrega": entrega_txt,
                "Vencimento": d.strftime("%d/%m/%Y"),
            }
        )
    st.dataframe(pd.DataFrame(_rows), hide_index=True, width="stretch")
    periodicidade = None
    data_inicial = None
else:
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

    data_inicial = st.date_input(
        "Data inicial do pagamento",
        key="data_inicial",
        format="DD/MM/YYYY",
    )


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

        nparc = int(qtd_parcelas)
        parcelas_insert = []
        valor_base = round(total_geral / nparc, 2)

        if st.session_state.cond_pg_modo == "dias":
            fk_sv = st.session_state.form_key
            prazos_salvar = [
                int(st.session_state.get(f"prazo_parcela_{i}_{fk_sv}", 0))
                for i in range(nparc)
            ]
            datas_pg = _datas_vencimento_por_prazos(data_chegada, prazos_salvar)
            for i in range(nparc):
                if i == nparc - 1:
                    valor_parcela = round(
                        total_geral - (valor_base * (nparc - 1)), 2
                    )
                else:
                    valor_parcela = valor_base
                parcelas_insert.append(
                    {
                        "numero_parcela": i + 1,
                        "valor_parcela": valor_parcela,
                        "data_pagamento": datas_pg[i].strftime("%Y-%m-%d"),
                    }
                )
        else:
            for i in range(nparc):
                if i == nparc - 1:
                    valor_parcela = round(
                        total_geral - (valor_base * (nparc - 1)), 2
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

        _invalidar_cache_pedidos_resumo()
        _limpar_estado_formulario_cadastro()
        st.rerun()

    except Exception as e:
        st.error(f"Erro ao salvar: {e}")