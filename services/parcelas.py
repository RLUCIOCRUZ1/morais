from datetime import timedelta
from dateutil.relativedelta import relativedelta


def gerar_parcelas(valor_total, qtd_parcelas, periodicidade, data_inicial):
    parcelas = []

    valor_base = round(valor_total / qtd_parcelas, 2)
    soma = 0

    for i in range(qtd_parcelas):

        if periodicidade == "SEMANAL":
            data = data_inicial + timedelta(weeks=i)

        elif periodicidade == "MENSAL":
            data = data_inicial + relativedelta(months=i)

        elif periodicidade == "ANUAL":
            data = data_inicial + relativedelta(years=i)

        else:  # UNICA
            data = data_inicial

        valor = valor_base

        # ajuste de centavos na última parcela
        if i == qtd_parcelas - 1:
            valor = round(valor_total - soma, 2)

        soma += valor

        parcelas.append({
            "numero": i + 1,
            "data_vencimento": data,
            "valor": valor
        })

    return parcelas