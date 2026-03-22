"""
simulate_30days.py — Simulacao de sustentabilidade financeira 30 dias.

Cenario:
  - 6 correntistas reais do banco de dados
  - Cada correntista deposita ~R$50 no inicio do mes (saldo inicial simulado)
  - Durante 30 dias cada um realiza transacoes plausíveis:
      * Pagamento via QR Code (PIX recebimento externo — correntista gera cobranca)
      * Envio de PIX por chave para terceiro
      * Pagamento de corrida (Uber/99) via PIX outbound
  - Sem transferencias internas (taxa zero)
  - Taxas aplicadas com precisao Decimal:
      * Taxa Asaas por operacao outbound: R$2.00 (apos cota gratuita mensal)
      * Taxa BioCodeTechPay outbound PF: R$2.50 flat
      * Taxa BioCodeTechPay outbound PJ: max(R$3.00, 0.80% * valor)
      * Taxa BioCodeTechPay inbound PF: R$0.00
      * Taxa BioCodeTechPay inbound PJ: max(R$0.49, 0.49% * valor)
  - Cota gratuita Asaas: 100 transferencias/mes (compartilhada pela plataforma)
  - Output: diario por correntista, resumo final, veredicto de sustentabilidade

Rodar: python scripts/simulate_30days.py
"""
import sys
import os
import random
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.fees import (
    calculate_pix_outbound_fee,
    calculate_pix_receive_fee,
    ASAAS_PIX_OUTBOUND_COST,
    ASAAS_PIX_FREE_MONTHLY,
)

TWO = Decimal("0.01")
SEED = 42
random.seed(SEED)


# ── Estruturas de dados -------------------------------------------------

@dataclass
class Customer:
    name: str
    email: str
    cpf_cnpj: str
    tipo: str           # PF ou PJ
    balance: Decimal
    real_balance: Decimal  # saldo real no banco de dados

@dataclass
class TxRecord:
    day: int
    customer: str
    tipo_tx: str      # SEND_PIX | PAY_QR | PAY_RIDE
    value: Decimal
    fee_platform: Decimal
    fee_asaas: Decimal
    margin: Decimal
    balance_after: Decimal
    note: str

# ── CENARIO: 6 correntistas PF, gasto mensal ~R$200 cada ---------------
# Todos forcados como Pessoa Fisica (tipo="PF").
# Saldo inicial = R$300 (R$200 em gastos + ~R$50 em taxas + R$50 de folga).
# Objetivo: medir exatamente quanto de taxa a plataforma arrecada.

_CUSTOMERS_RAW = [
    # (nome, email, cpf_cnpj)
    ("Cezar Cola",                        "homeopatiaenaturopatia@gmail.com", "24455140000112"),
    ("Hellen Cardoso",                    "hellen.nutricao@outlook.com",      "44147614841"  ),
    ("Sergio Santos de melo",             "azusa@institutoazusa.com.be",      "02193446806"  ),
    ("Cezi Cola",                         "cezicolatecnologia@gmail.com",     "35060268870"  ),
    ("Karen Passe Silva Brito Oliveira",  "karenpassibrioli@gmail.com",       "22317665822"  ),
    ("Conta Sistema / Teste",             "novo.correntista@biocode.com",     "00000000000"  ),
]

def load_customers() -> List[Customer]:
    result = []
    for name, email, cpf_cnpj in _CUSTOMERS_RAW:
        result.append(Customer(
            name=name,
            email=email,
            cpf_cnpj=cpf_cnpj,
            tipo="PF",                  # todos Pessoa Fisica neste cenario
            balance=Decimal("300.00"),  # saldo inicial: R$200 gasto + R$100 buffer
            real_balance=Decimal("0.00"),
        ))
    return result


# ── Gerador de transacoes por dia --------------------------------------

# Valores ajustados para perfil de gasto mensal ~R$200 por correntista PF.
# Media outbound: ~R$27 por transacao. Para gastar R$200: ~7-8 transacoes/mes.
RIDE_VALUES  = [12, 15, 18, 22, 25, 30, 35]
QR_VALUES    = [10, 15, 20, 25, 30, 40]
SEND_VALUES  = [20, 25, 30, 35, 40, 50]

def generate_daily_txs(
    customer: Customer,
    day: int,
    asaas_free_remaining: int,
) -> Tuple[List[TxRecord], int, int]:
    """
    Gera 1 a 3 transacoes plausíveis para o dia.
    Retorna (lista_transacoes, asaas_free_remaining_pos, outbound_count).
    """
    records = []

    # Nao opera se saldo insuficiente para cobrir qualquer taxa
    if customer.balance < Decimal("3.00"):
        return records, asaas_free_remaining, 0

    # Quantas operacoes hoje? 0 a 3, ponderado (maioria dos dias 1–2)
    n_ops = random.choices([0, 1, 2, 3], weights=[15, 40, 35, 10])[0]
    outbound_today = 0

    for _ in range(n_ops):
        if customer.balance < Decimal("3.00"):
            break

        op = random.choices(
            ["SEND_PIX", "PAY_RIDE", "PAY_QR"],
            weights=[35, 35, 30],
        )[0]

        if op in ("SEND_PIX", "PAY_RIDE"):
            # Outbound — consome saldo + taxa plataforma
            value = Decimal(str(random.choice(RIDE_VALUES if op == "PAY_RIDE" else SEND_VALUES)))
            fee_platform = calculate_pix_outbound_fee(customer.cpf_cnpj, float(value))
            total_debit = value + fee_platform

            if total_debit > customer.balance:
                continue  # sem saldo suficiente — pula esta operacao

            # Custo Asaas: R$2.00 apos cota gratuita
            if asaas_free_remaining > 0:
                fee_asaas = Decimal("0.00")
                asaas_free_remaining -= 1
            else:
                fee_asaas = ASAAS_PIX_OUTBOUND_COST

            margin_net = fee_platform - fee_asaas
            customer.balance = (customer.balance - total_debit).quantize(TWO, ROUND_HALF_UP)
            outbound_today += 1
            note = "Uber/99" if op == "PAY_RIDE" else "PIX enviado"

            records.append(TxRecord(
                day=day,
                customer=customer.name,
                tipo_tx=op,
                value=value,
                fee_platform=fee_platform,
                fee_asaas=fee_asaas,
                margin=margin_net,
                balance_after=customer.balance,
                note=note,
            ))

        else:  # PAY_QR — recebimento de PIX externo via QR Code
            value = Decimal(str(random.choice(QR_VALUES)))
            fee_platform = calculate_pix_receive_fee(customer.cpf_cnpj, float(value))
            fee_asaas = Decimal("0.00")  # Asaas nao cobra por inbound no plano atual
            # Correntista recebe o valor bruto; plataforma desconta a taxa _no credito_
            net_credit = (value - fee_platform).quantize(TWO, ROUND_HALF_UP)
            margin_net = fee_platform  # pura margem (custo Asaas = 0)
            customer.balance = (customer.balance + net_credit).quantize(TWO, ROUND_HALF_UP)

            records.append(TxRecord(
                day=day,
                customer=customer.name,
                tipo_tx=op,
                value=value,
                fee_platform=fee_platform,
                fee_asaas=fee_asaas,
                margin=margin_net,
                balance_after=customer.balance,
                note="QR Code recebido",
            ))

    return records, asaas_free_remaining, outbound_today


# ── Simulacao principal -------------------------------------------------

def run_simulation():
    customers = load_customers()
    if not customers:
        print("[ERRO] Nenhum correntista encontrado no banco de dados.")
        sys.exit(1)

    n = len(customers)
    print(f"\n{'='*72}")
    print("  SIMULACAO 30 DIAS — BioCodeTechPay")
    print(f"  CENARIO: {n} correntistas PESSOA FISICA | gasto ~R$200 cada")
    print(f"  Taxa PF outbound: R$2,50 flat por transacao")
    print(f"  Saldo inicial por correntista: R$300,00")
    print(f"  Saldo inicial total injetado: R${300*n:.2f}")
    print(f"{'='*72}")
    print()
    for c in customers:
        print(f"  {c.tipo}  {c.name:<35}  saldo_real=R${float(c.real_balance):.2f}  doc={c.cpf_cnpj}")
    print()

    # Contadores globais
    all_txs: List[TxRecord] = []
    total_platform_revenue = Decimal("0.00")
    total_asaas_cost        = Decimal("0.00")
    total_net_margin        = Decimal("0.00")
    total_outbound          = 0
    asaas_free_remaining    = ASAAS_PIX_FREE_MONTHLY  # cota compartilhada do mes

    # Historico diario da plataforma
    daily_margin: List[Decimal] = []

    # ── 30 dias ---------------------------------------------------------
    for day in range(1, 31):
        day_margin = Decimal("0.00")
        day_outbound = 0

        for customer in customers:
            txs, asaas_free_remaining, ob = generate_daily_txs(
                customer, day, asaas_free_remaining
            )
            day_outbound += ob
            for tx in txs:
                all_txs.append(tx)
                total_platform_revenue += tx.fee_platform
                total_asaas_cost       += tx.fee_asaas
                total_net_margin       += tx.margin
                day_margin             += tx.margin

        total_outbound += day_outbound
        daily_margin.append(day_margin)

    # ── Saida por correntista -------------------------------------------
    print(f"{'='*72}")
    print("  EXTRATO POR CORRENTISTA (primeiras / ultimas operacoes)")
    print(f"{'='*72}")

    for customer in customers:
        ctxs = [t for t in all_txs if t.customer == customer.name]
        total_fees_paid   = sum(t.fee_platform for t in ctxs)
        total_spent       = sum(t.value for t in ctxs if t.tipo_tx in ("SEND_PIX","PAY_RIDE"))
        total_received    = sum(t.value for t in ctxs if t.tipo_tx == "PAY_QR")
        n_out = sum(1 for t in ctxs if t.tipo_tx in ("SEND_PIX","PAY_RIDE"))
        n_in  = sum(1 for t in ctxs if t.tipo_tx == "PAY_QR")

        print(f"\n  {customer.tipo}  {customer.name}")
        print(f"    Saldo inicial simulado : R$50,00")
        print(f"    Saldo final simulado   : R${float(customer.balance):.2f}")
        print(f"    Transacoes outbound    : {n_out}  |  inbound  : {n_in}  |  total: {len(ctxs)}")
        print(f"    Total enviado/gasto    : R${float(total_spent):.2f}")
        print(f"    Total recebido (bruto) : R${float(total_received):.2f}")
        print(f"    Total taxas pagas      : R${float(total_fees_paid):.2f}")

        # Ultimas 3 operacoes
        for tx in ctxs[-3:]:
            arrow = "-->" if tx.tipo_tx in ("SEND_PIX","PAY_RIDE") else "<--"
            print(f"    Dia {tx.day:02d} {arrow} {tx.tipo_tx:<10} R${float(tx.value):.2f}  "
                  f"fee=R${float(tx.fee_platform):.2f}  saldo_pos=R${float(tx.balance_after):.2f}  [{tx.note}]")

    # ── Resumo da plataforma --------------------------------------------
    print(f"\n{'='*72}")
    print("  RESUMO DA PLATAFORMA — 30 DIAS")
    print(f"{'='*72}")

    n_outbound_total = sum(1 for t in all_txs if t.tipo_tx in ("SEND_PIX","PAY_RIDE"))
    n_inbound_total  = sum(1 for t in all_txs if t.tipo_tx == "PAY_QR")
    free_used        = min(ASAAS_PIX_FREE_MONTHLY, n_outbound_total)
    paid_asaas_ops   = max(0, n_outbound_total - ASAAS_PIX_FREE_MONTHLY)

    print(f"  Total de transacoes            : {len(all_txs)}")
    print(f"  Outbound (SEND+RIDE)           : {n_outbound_total}")
    print(f"    Dentro da cota gratuita Asaas: {free_used}")
    print(f"    Cobradas a R$2,00 pela Asaas : {paid_asaas_ops}")
    print(f"  Inbound (QR Code)              : {n_inbound_total}")
    print(f"")
    print(f"  Receita bruta plataforma       : R${float(total_platform_revenue):.2f}")
    print(f"  Custo total Asaas              : R${float(total_asaas_cost):.2f}")
    print(f"  Margem liquida plataforma      : R${float(total_net_margin):.2f}")
    print(f"")

    # Margem por semana
    print(f"  Margem semanal:")
    weeks = [daily_margin[i*7:(i+1)*7] for i in range(4)] + [daily_margin[28:]]
    for wi, wk in enumerate(weeks):
        if wk:
            s = sum(wk)
            print(f"    Semana {wi+1}: R${float(s):.2f}  ({'positiva' if s>0 else 'NEGATIVA'})")

    # Linha do tempo: dias com margem negativa
    neg_days = [i+1 for i,m in enumerate(daily_margin) if m < Decimal("0.00")]
    zero_days = [i+1 for i,m in enumerate(daily_margin) if m == Decimal("0.00")]
    print(f"")
    print(f"  Dias com margem negativa       : {len(neg_days)}  {neg_days}")
    print(f"  Dias com margem zero           : {len(zero_days)}")
    print(f"  Dias com margem positiva       : {30 - len(neg_days) - len(zero_days)}")

    # Saldo correntistas apos 30 dias
    total_custsaldo = sum(c.balance for c in customers)
    inicial_total   = Decimal("50.00") * n
    delta_custsaldo = total_custsaldo - inicial_total
    print(f"")
    print(f"  Saldo total correntistas ANTES : R${float(inicial_total):.2f}")
    print(f"  Saldo total correntistas APOS  : R${float(total_custsaldo):.2f}")
    print(f"  Variacao liquida (normal — txs saíram): R${float(delta_custsaldo):.2f}")

    # ── Veredicto de sustentabilidade ----------------------------------
    print(f"\n{'='*72}")
    print("  VEREDICTO DE SUSTENTABILIDADE")
    print(f"{'='*72}")
    print()

    # 1. Margem cobre custos?
    margin_positive = total_net_margin > Decimal("0.00")

    # 2. Custo Asaas total vs receita
    asaas_coverage_ratio = (
        float(total_platform_revenue) / float(total_asaas_cost)
        if total_asaas_cost > Decimal("0.00")
        else float("inf")
    )

    # 3. Capacidade de escala: com 6 users, quanto precisaria de volume?
    monthly_net_per_user = float(total_net_margin) / n if n else 0
    breakeven_monthly_users = (
        int(20.00 / monthly_net_per_user) if monthly_net_per_user > 0 else float("inf")
    )

    # 4. Cota gratuita Asaas — quanto dela foi consumida?
    cota_pct = (free_used / ASAAS_PIX_FREE_MONTHLY) * 100

    print(f"  Margem liquida 30 dias         : R${float(total_net_margin):.2f}")
    print(f"  Margem por usuario/mes         : R${monthly_net_per_user:.2f}")
    print(f"  Cota gratuita Asaas consumida  : {cota_pct:.1f}% ({free_used}/{ASAAS_PIX_FREE_MONTHLY})")
    print(f"  Cobertura de custos Asaas      : {asaas_coverage_ratio:.1f}x  (receita / custo Asaas)")
    print()

    if margin_positive and total_net_margin >= Decimal("5.00"):
        status = "SUSTENTAVEL"
        icon = "[OK]"
    elif margin_positive:
        status = "MARGINALMENTE POSITIVO — base muito pequena"
        icon = "[ATENCAO]"
    else:
        status = "INSUSTENTAVEL — prejuizo operacional no mes"
        icon = "[CRITICO]"

    print(f"  Status: {icon}  {status}")
    print()

    # Explicacao detalhada
    print("  Analise:")
    if n_outbound_total <= ASAAS_PIX_FREE_MONTHLY:
        print(f"  - TODOS os outbounds ({n_outbound_total}) ficaram dentro da cota gratuita Asaas.")
        print(f"    Custo Asaas real no periodo = R$0,00. Receita de taxa = lucro puro.")
    else:
        print(f"  - {paid_asaas_ops} outbounds ultrapassaram a cota gratuita.")
        print(f"    Asaas cobrou R$2,00 x {paid_asaas_ops} = R${paid_asaas_ops*2:.2f}.")
        print(f"    Taxa BioCodeTechPay cobriu: R${float(total_platform_revenue):.2f}.")
        print(f"    Margem liquida: R${float(total_net_margin):.2f}.")

    if n_inbound_total > 0:
        inbound_rev = sum(t.fee_platform for t in all_txs if t.tipo_tx == "PAY_QR")
        print(f"  - Receita inbound (QR Code): R${float(inbound_rev):.2f}  (custo Asaas = R$0,00 — margem pura).")

    print()
    print(f"  Com 6 correntistas gastando R$50/mes o banco gera R${float(total_net_margin):.2f}/mes.")
    if monthly_net_per_user > 0:
        print(f"  Para gerar R$1.000/mes de margem liquida: seria necessario ~{int(1000/monthly_net_per_user)} usuarios ativos.")
        print(f"  Para gerar R$5.000/mes: ~{int(5000/monthly_net_per_user)} usuarios ativos.")

    print()
    print(f"  Risco principal identificado:")
    if n_outbound_total > ASAAS_PIX_FREE_MONTHLY * 0.8:
        print(f"  - Volume de outbounds ({n_outbound_total}) ja aproxima o limite da cota gratuita Asaas ({ASAAS_PIX_FREE_MONTHLY}).")
        print(f"    Com crescimento, o custo Asaas aumenta R$2,00/tx apos o limite.")
        print(f"    A taxa minima (R$2,50 PF / R$3,00 PJ) garante margem positiva mesmo apos o limite.")
    else:
        print(f"  - Volume ainda longe do limite da cota Asaas. Sem risco imediato de custo extra.")

    print()
    print(f"  Conclusao final:")
    if margin_positive:
        print(f"  O banco NAO quebrara neste cenario. A estrutura de taxas cobre os custos Asaas")
        print(f"  e gera margem positiva mesmo com base de apenas {n} usuarios e R$50 de saldo.")
        print(f"  A viabilidade financeira depende de escala — com {int(200/monthly_net_per_user) if monthly_net_per_user>0 else 'N/A'} usuarios")
        print(f"  o modelo ja cobre custos operacionais basicos de uma fintech enxuta.")
    else:
        print(f"  Atencao: com a taxa e volume atuais, o mes termina com prejuizo.")
        print(f"  Revisar: preco minimo da taxa de saida ou aumentar base de usuarios.")

    print(f"\n{'='*72}\n")

    return {
        "status": status,
        "net_margin_30d": float(total_net_margin),
        "platform_revenue": float(total_platform_revenue),
        "asaas_cost": float(total_asaas_cost),
        "total_txs": len(all_txs),
        "n_customers": n,
    }


if __name__ == "__main__":
    run_simulation()
