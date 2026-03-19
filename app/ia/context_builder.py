"""
Context Builder — transforms engine outputs into a structured LLM context block.
The LLM receives only computed results. No raw DB data, no PII.
"""
from app.ia.schemas import FinancialSnapshot, WealthScore, CashflowWindow, StrategyPlan, SimulationResult


def _format_transaction_line(tx) -> str:
    """Format a single transaction summary for the context block."""
    date_str = tx.date.strftime("%d/%m") if tx.date else "?"
    fee_part = f" (taxa R$ {tx.fee:.2f})" if tx.fee > 0 else ""
    return f"  {tx.type} R$ {tx.amount:.2f} em {date_str}{fee_part}"


def _format_simulation(sim: SimulationResult) -> str:
    """Format wealth simulation for the context block."""
    return (
        f"Simulacao patrimonial (aporte R$ {sim.monthly_investment:.2f}/mes a {sim.annual_rate * 100:.0f}% a.a.):\n"
        f"  5 anos: R$ {sim.year_5:,.2f} | 10 anos: R$ {sim.year_10:,.2f} | "
        f"20 anos: R$ {sim.year_20:,.2f} | 30 anos: R$ {sim.year_30:,.2f}"
    )


def build_llm_context(
    snapshot: FinancialSnapshot,
    wealth: WealthScore,
    cashflow: CashflowWindow,
    strategy: StrategyPlan,
    simulation: SimulationResult | None = None,
) -> str:
    """
    Builds the CONTEXT block injected between system prompt and user message.
    Compact plaintext — never includes CPF, names, keys or account IDs.
    """
    alerts_str = "; ".join(cashflow.alerts) if cashflow.alerts else "nenhum"
    notes_str = " | ".join(strategy.notes) if strategy.notes else ""

    tx_lines = "\n".join(
        _format_transaction_line(tx) for tx in snapshot.recent_transactions
    ) if snapshot.recent_transactions else "  nenhuma"

    ctx = (
        "--- CONTEXTO FINANCEIRO (dados reais da conta, tempo real) ---\n"
        f"Saldo atual: R$ {snapshot.balance:.2f}\n"
        f"Ultimos 30 dias:\n"
        f"  Recebido:         R$ {snapshot.last_30d_received:.2f}\n"
        f"  Gasto:            R$ {snapshot.last_30d_sent:.2f}\n"
        f"  Liquido (net):    R$ {snapshot.net_cashflow:.2f}\n"
        f"  Taxa de poupanca: {snapshot.savings_rate * 100:.1f}%\n"
        f"  Transacoes:       {snapshot.total_transactions_30d}\n"
        f"\n"
        f"Ultimas transacoes:\n{tx_lines}\n"
        f"\n"
        f"Wealth Score: {wealth.score}/100 ({wealth.label})\n"
        f"  Breakdown: poupanca {wealth.savings_rate_score}/40 | liquidez {wealth.liquidity_score}/30 | "
        f"atividade {wealth.activity_score}/15 | verificacao {wealth.verification_score}/15\n"
        f"  Capacidade de poupanca mensal: R$ {wealth.savings_capacity:.2f}\n"
        f"  Cobertura de emergencia atual: {wealth.emergency_fund_months:.1f} meses\n"
        f"\n"
        f"Cashflow (30 dias):\n"
        f"  Gasto medio diario: R$ {cashflow.avg_daily_outbound:.2f}\n"
        f"  Burn rate:          {cashflow.burn_rate_days:.0f} dias de runway\n"
        f"  Alertas: {alerts_str}\n"
        f"\n"
        f"Estrategia recomendada (deterministica):\n"
        f"  Prioridade:                 {strategy.priority}\n"
        f"  Poupanca mensal recomendada: R$ {strategy.monthly_savings_target:.2f}\n"
        f"  Reserva de emergencia pendente: R$ {strategy.emergency_fund_remaining:.2f}\n"
        f"  Investimento sugerido:      {strategy.investment_suggestion}\n"
        + (f"  Notas: {notes_str}\n" if notes_str else "")
    )

    if simulation and simulation.monthly_investment > 0:
        ctx += f"\n{_format_simulation(simulation)}\n"

    ctx += "--- FIM DO CONTEXTO ---"
    return ctx
