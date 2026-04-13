from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "Defina SUPABASE_URL e SUPABASE_KEY no arquivo .env na raiz do projeto."
    )

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# =========================
# FUNÇÕES
# =========================

def inserir_pedido(dados):
    response = supabase.table("pedidos").insert(dados).execute()
    return response.data


def inserir_itens(itens):
    response = supabase.table("pedido_itens").insert(itens).execute()
    return response.data


def inserir_parcelas(parcelas):
    response = supabase.table("pedido_parcelas").insert(parcelas).execute()
    return response.data


def listar_condicoes_pagamento():
    """Condições reutilizáveis (dias após chegada). Retorna [] se a tabela não existir."""
    try:
        response = (
            supabase.table("condicoes_pagamento")
            .select("id, nome, qtd_parcelas, prazos_dias")
            .order("nome")
            .execute()
        )
        return response.data or []
    except Exception:
        return []


def inserir_condicao_pagamento(nome: str, qtd_parcelas: int, prazos_dias: list):
    """prazos_dias: lista de inteiros, mesmo tamanho que qtd_parcelas."""
    row = {
        "nome": nome.strip(),
        "qtd_parcelas": int(qtd_parcelas),
        "prazos_dias": [int(x) for x in prazos_dias],
    }
    response = supabase.table("condicoes_pagamento").insert(row).execute()
    return response.data


def excluir_condicao_pagamento(condicao_id: int):
    supabase.table("condicoes_pagamento").delete().eq("id", condicao_id).execute()


def listar_pedidos_resumo(limite=500):
    """Lista pedidos para edição / recebimento (mais recentes primeiro).

    Funciona mesmo sem as colunas `recebido` / `data_recebimento` (migração opcional).
    """
    consultas = (
        "id, fornecedor, grupo, marca, data_chegada, total_quantidade, total_valor, recebido, data_recebimento",
        "id, fornecedor, grupo, marca, data_chegada, total_quantidade, total_valor",
    )
    dados = None
    for cols in consultas:
        try:
            response = (
                supabase.table("pedidos")
                .select(cols)
                .order("id", desc=True)
                .limit(limite)
                .execute()
            )
            dados = response.data or []
            break
        except Exception:
            continue
    if dados is None:
        return []
    for row in dados:
        row.setdefault("recebido", False)
        row.setdefault("data_recebimento", None)
    return dados


def fetch_parcelas_para_financeiro():
    """Carrega parcelas; tenta incluir `pago` e `data_quitacao` se existirem."""
    consultas = (
        "id, pedido_id, numero_parcela, valor_parcela, data_pagamento, pago, data_quitacao",
        "id, pedido_id, numero_parcela, valor_parcela, data_pagamento, pago",
        "id, pedido_id, numero_parcela, valor_parcela, data_pagamento",
    )
    for cols in consultas:
        try:
            response = supabase.table("pedido_parcelas").select(cols).execute()
            data = response.data or []
            return data, ("pago" in cols)
        except Exception:
            continue
    return [], False


def buscar_pedido_completo(pedido_id):
    """Evita `.single()` (quebra se não houver linha)."""
    ped = (
        supabase.table("pedidos")
        .select("*")
        .eq("id", pedido_id)
        .limit(1)
        .execute()
    )
    if not ped.data:
        return None, [], []
    row_ped = ped.data[0]
    itens = (
        supabase.table("pedido_itens")
        .select("*")
        .eq("pedido_id", pedido_id)
        .execute()
    )
    pars = (
        supabase.table("pedido_parcelas")
        .select("*")
        .eq("pedido_id", pedido_id)
        .order("numero_parcela")
        .execute()
    )
    return row_ped, itens.data or [], pars.data or []


def atualizar_pedido(pedido_id, dados):
    response = supabase.table("pedidos").update(dados).eq("id", pedido_id).execute()
    return response.data


def deletar_itens_pedido(pedido_id):
    supabase.table("pedido_itens").delete().eq("pedido_id", pedido_id).execute()


def deletar_parcelas_pedido(pedido_id):
    supabase.table("pedido_parcelas").delete().eq("pedido_id", pedido_id).execute()


def excluir_pedido_completo(pedido_id):
    """Apaga parcelas, itens e o pedido (ordem compatível com FKs)."""
    deletar_parcelas_pedido(pedido_id)
    deletar_itens_pedido(pedido_id)
    supabase.table("pedidos").delete().eq("id", pedido_id).execute()


def data_baixa_hoje_iso():
    """Data de hoje no fuso Brasil (para registrar o clique na baixa)."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    except Exception:
        from datetime import date

        return date.today().isoformat()


def atualizar_parcela_pago(parcela_id, pago, data_quitacao=None):
    """Marca parcela paga e grava data_quitacao; ao desmarcar, limpa a data.

    Sem fallback parcial: se o update falhar (ex.: coluna ou RLS), o erro sobe
    para não gravar só `pago` sem a data.
    """
    dados = {"pago": bool(pago)}
    if pago:
        dados["data_quitacao"] = data_quitacao or data_baixa_hoje_iso()
    else:
        dados["data_quitacao"] = None
    try:
        response = (
            supabase.table("pedido_parcelas")
            .update(dados)
            .eq("id", parcela_id)
            .execute()
        )
        return response.data
    except Exception as e:
        err = str(e).lower()
        if "data_quitacao" in err or "pgrst204" in err:
            raise RuntimeError(
                "No Supabase, abra SQL Editor e execute (uma vez):\n\n"
                "ALTER TABLE pedido_parcelas "
                "ADD COLUMN IF NOT EXISTS data_quitacao date;\n\n"
                "Depois atualize a página do dashboard."
            ) from e
        raise


def atualizar_pedido_recebimento(pedido_id, recebido, data_recebimento=None):
    """Ao marcar recebido sem informar data, grava a data de hoje (fuso Brasil)."""
    dados = {"recebido": bool(recebido)}
    if recebido is False:
        dados["data_recebimento"] = None
    else:
        dados["data_recebimento"] = data_recebimento or data_baixa_hoje_iso()
    response = supabase.table("pedidos").update(dados).eq("id", pedido_id).execute()
    return response.data


def buscar_dados_otb():
    response = supabase.table("vw_otb").select("*").execute()
    return response.data


def _fetch_table_all_pages(table: str, columns: str, page_size: int = 1000) -> list:
    """Lê todas as linhas (PostgREST limita ~1000 por request sem paginar)."""
    all_rows: list = []
    start = 0
    while True:
        end = start + page_size - 1
        resp = supabase.table(table).select(columns).range(start, end).execute()
        batch = resp.data or []
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return all_rows


def _coerce_recebido_bool(series):
    """Evita tratar string 'false' como True ao converter para bool."""
    import pandas as pd

    def one(x):
        if x is None:
            return False
        try:
            if pd.isna(x):
                return False
        except (TypeError, ValueError):
            pass
        if isinstance(x, bool):
            return x
        if isinstance(x, (int, float)):
            return bool(int(x))
        s = str(x).strip().lower()
        if s in ("true", "t", "1", "yes", "sim"):
            return True
        if s in ("false", "f", "0", "no", "não", "nao", ""):
            return False
        return bool(x)

    return series.map(one)


def fetch_otb_pipeline(somente_nao_recebidos: bool = True):
    """Monta o OTB a partir de itens + pedidos.

    - ``somente_nao_recebidos=True`` (padrão): igual ao fluxo "em aberto".
    - ``False``: inclui também pedidos já recebidos (para ver todos os grupos no OTB).

    O mês vem da **data_chegada**; sem data usa o 1º dia do mês atual (Brasil).
    """
    import pandas as pd

    items = _fetch_table_all_pages(
        "pedido_itens", "pedido_id, referencia, quantidade, custo_total"
    )
    cols = ["grupo", "marca", "referencia", "mes", "total_qtd", "total_valor", "data_recebimento"]
    if not items:
        return pd.DataFrame(columns=cols)

    ids = sorted(
        {int(x["pedido_id"]) for x in items if x.get("pedido_id") is not None}
    )
    if not ids:
        return pd.DataFrame(columns=cols)

    all_peds: list = []
    step = 100
    for i in range(0, len(ids), step):
        chunk = ids[i : i + step]
        resp = (
            supabase.table("pedidos")
            .select("id, grupo, marca, data_chegada, recebido, data_recebimento")
            .in_("id", chunk)
            .execute()
        )
        all_peds.extend(resp.data or [])

    df_i = pd.DataFrame(items)
    df_p = pd.DataFrame(all_peds)
    if df_p.empty:
        return pd.DataFrame(columns=cols)

    df_i["pedido_id"] = pd.to_numeric(df_i["pedido_id"], errors="coerce")
    df_p["id"] = pd.to_numeric(df_p["id"], errors="coerce")
    df_i = df_i.dropna(subset=["pedido_id"])
    df_p = df_p.dropna(subset=["id"])

    if "recebido" not in df_p.columns:
        df_p["recebido"] = False
    else:
        df_p["recebido"] = _coerce_recebido_bool(df_p["recebido"])

    if "data_recebimento" not in df_p.columns:
        df_p["data_recebimento"] = pd.NaT
    else:
        df_p["data_recebimento"] = pd.to_datetime(df_p["data_recebimento"], errors="coerce")

    m = df_i.merge(df_p, left_on="pedido_id", right_on="id", how="inner", suffixes=("", "_ped"))
    if m.empty:
        return pd.DataFrame(columns=cols)

    # Recebido no banco mas sem data (cadastros antigos): exibir como hoje no OTB
    fill_mask = m["recebido"] & m["data_recebimento"].isna()
    if fill_mask.any():
        m.loc[fill_mask, "data_recebimento"] = pd.to_datetime(data_baixa_hoje_iso())

    if somente_nao_recebidos:
        m = m.loc[~m["recebido"]]
        if m.empty:
            return pd.DataFrame(columns=cols)

    m["data_chegada"] = pd.to_datetime(m["data_chegada"], errors="coerce")
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        br = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        hoje_mes = pd.Timestamp(br.year, br.month, 1)
    except Exception:
        hoje_mes = pd.Timestamp.now().normalize().replace(day=1)
    m.loc[m["data_chegada"].isna(), "data_chegada"] = hoje_mes

    m["mes"] = m["data_chegada"].dt.to_period("M").dt.to_timestamp()
    agg = m.groupby(["grupo", "marca", "referencia", "mes"], as_index=False).agg(
        total_qtd=("quantidade", "sum"),
        total_valor=("custo_total", "sum"),
        data_recebimento=("data_recebimento", "max"),
    )
    return agg


def fetch_otb_aberto_pipeline():
    """Compatível: só pedidos não recebidos."""
    return fetch_otb_pipeline(somente_nao_recebidos=True)

