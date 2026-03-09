# Bio Code Tech Pay — Roadmap Tecnico
## Modulo de Taxas + Inteligencia Artificial Financeira

**Status:** Standby — pronto para implementacao
**Versao:** 1.0
**Data:** 2026-03-09
**Autor:** Cezi Cola Senior Software Engineer

---

## Parte 1 — Politica de Taxas por Transacao

### 1.1 Principio de Design

- Pessoa fisica com PIX e transferencia interna: gratuito (obrigatorio para competitividade no mercado brasileiro — referencia BCB Resolucao 1 de 2020)
- Monetizacao via servicos de valor agregado: IA Premium, recebimento B2B, credito
- Isenção total para conta(s) admin definidas por configuracao
- Taxa calculada antes da transacao, debitada atomicamente no mesmo commit

### 1.2 Tabela de Taxas

| Tipo de Transacao | Conta PF Free | Conta PF Premium | Conta PJ/Comerciante | Conta Admin |
|---|---|---|---|---|
| PIX entre contas Bio Code Pay | 0% | 0% | 0% | 0% |
| PIX para chave externa (CPF/CNPJ/email/cel) | 0% | 0% | 0.5% | 0% |
| Recebimento via QR Code estatico | 0% | 0% | 0.99% + R$0,10 | 0% |
| Recebimento via link de pagamento | 0% | 0% | 1.2% | 0% |
| Saque em ATM parceiro | R$2,90/saque | R$1,90/saque | R$1,90/saque | 0% |
| Transferencia internacional (futuro) | N/A | 1.5% | 1.5% | 0% |
| Antecipacao de recebivel (futuro) | N/A | spread 2-4% a.m. | spread 2-4% a.m. | 0% |
| Assinatura IA Premium | — | R$9,90/mes | R$19,90/mes | 0% |

### 1.3 Contas Isentas (configuracao em .env)

```
EXEMPT_ACCOUNT_EMAILS=biocodetechnology@gmail.com
```

Multiplas contas separadas por virgula. Lidas na startup. Nunca hardcoded no codigo de negocio.

### 1.4 Estrutura do Modulo de Taxas

```
app/
  fees/
    __init__.py
    policy.py          # FeePolicy: calcula taxa por tipo + perfil de conta
    schemas.py         # FeeBreakdown: valor_bruto, taxa_absoluta, taxa_percentual, valor_liquido
    models.py          # FeeTransaction: ledger de taxas cobradas (auditoria)
    router.py          # GET /fees/preview, GET /fees/history
    service.py         # aplica taxa atomicamente, registra no ledger
```

### 1.5 Contrato do FeePolicy (Python)

```python
# app/fees/policy.py

from dataclasses import dataclass
from enum import Enum

class TransactionType(str, Enum):
    PIX_INTERNAL       = "pix_internal"
    PIX_EXTERNAL       = "pix_external"
    QR_CODE_RECEIVE    = "qr_receive"
    BOLETO_PAY         = "boleto_pay"
    ATM_WITHDRAWAL     = "atm_withdrawal"
    INTL_TRANSFER      = "international_transfer"

@dataclass
class FeeBreakdown:
    gross_value: float
    fee_absolute: float     # valor fixo (ex: R$0,10)
    fee_rate: float         # percentual (ex: 0.0099)
    fee_total: float        # fee_absolute + gross_value * fee_rate
    net_value: float        # gross_value - fee_total (para o destinatario)
    revenue_value: float    # fee_total vai para conta admin

class FeePolicy:
    def __init__(self, exempt_emails: set[str]):
        self._exempt = exempt_emails

    def calculate(
        self,
        user_email: str,
        account_type: str,   # "pf_free" | "pf_premium" | "pj"
        tx_type: TransactionType,
        value: float
    ) -> FeeBreakdown:
        if user_email in self._exempt:
            return FeeBreakdown(value, 0, 0, 0, value, 0)
        rate, fixed = self._lookup(account_type, tx_type)
        fee_total = round(value * rate + fixed, 2)
        return FeeBreakdown(
            gross_value=value,
            fee_absolute=fixed,
            fee_rate=rate,
            fee_total=fee_total,
            net_value=round(value - fee_total, 2),
            revenue_value=fee_total
        )

    def _lookup(self, account_type: str, tx_type: TransactionType) -> tuple[float, float]:
        table = {
            ("pf_free",     TransactionType.PIX_INTERNAL):    (0.0,    0.0),
            ("pf_free",     TransactionType.PIX_EXTERNAL):    (0.0,    0.0),
            ("pf_free",     TransactionType.QR_CODE_RECEIVE): (0.0,    0.0),
            ("pj",          TransactionType.PIX_EXTERNAL):    (0.005,  0.0),
            ("pj",          TransactionType.QR_CODE_RECEIVE): (0.0099, 0.10),
        }
        return table.get((account_type, tx_type), (0.0, 0.0))
```

### 1.6 Integracao no Router PIX (ponto de aplicacao)

Taxa deve ser calculada e aplicada **atomicamente** dentro do mesmo `db.commit()` da transacao:

```python
# Em app/pix/router.py — trecho de integracao futura
fee = fee_policy.calculate(
    user_email=sender.email,
    account_type=sender.account_type,   # campo a adicionar em User
    tx_type=TransactionType.PIX_EXTERNAL,
    value=payment_value
)
if fee.fee_total > 0:
    sender.balance -= fee.fee_total
    admin_account.balance += fee.revenue_value
    fee_ledger = FeeLedger(
        user_id=sender.id,
        transaction_id=pix_tx.id,
        fee_total=fee.fee_total,
        fee_rate=fee.fee_rate,
        description=f"Taxa PIX externo {fee.fee_rate*100:.2f}%"
    )
    db.add(fee_ledger)
# Tudo no mesmo db.commit() da transacao principal
```

### 1.7 Migracao de Banco Necessaria

```sql
-- Adicionar coluna account_type em users
ALTER TABLE users ADD COLUMN account_type VARCHAR(20) NOT NULL DEFAULT 'pf_free';

-- Criar tabela de ledger de taxas
CREATE TABLE fee_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    transaction_id VARCHAR(36),
    fee_total FLOAT NOT NULL,
    fee_rate FLOAT NOT NULL,
    fee_absolute FLOAT NOT NULL DEFAULT 0,
    description VARCHAR(200),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
CREATE INDEX idx_fee_user ON fee_ledger(user_id);
CREATE INDEX idx_fee_transaction ON fee_ledger(transaction_id);
```

---

## Parte 2 — Inteligencia Artificial Financeira

### 2.1 Visao do Produto

Nenhum banco brasileiro oferece hoje:

1. Conselheiro financeiro conversacional com contexto real de transacoes
2. Previsao de fluxo de caixa pessoal proativa
3. Score de saude financeira em tempo real com acoes sugeridas
4. Seguranca semantica — deteccao de fraude por comportamento, nao so por regra
5. Roteamento inteligente entre 29 modelos para otimizar custo vs qualidade

### 2.2 Arquitetura do Modulo AI

```
app/
  ai/
    __init__.py
    router.py              # POST /ai/chat, GET /ai/insights, GET /ai/score, GET /ai/security-report
    service.py             # orquestrador principal — decide modelo, constroi contexto, interpreta resposta
    schemas.py             # ChatRequest, ChatResponse, InsightResponse, HealthScore, SecurityAlert
    model_router.py        # OpenRouter client + selecao de modelo por task_type + budget
    context_builder.py     # constroi contexto financeiro anonimizado do usuario para o LLM
    prompt_templates.py    # prompts versionados por funcionalidade
    guardrails.py          # validacao de output: sem conselhos de investimento ilegais, sem dados sensiveis
    security_scanner.py    # analisa padroes de acesso e transacoes para detectar anomalias
    prompts/
      financial_advisor.txt
      cashflow_forecast.txt
      fraud_analysis.txt
      security_audit.txt
      health_score.txt
```

### 2.3 OpenRouter — Roteamento de Modelos

Chave de API: `OPENROUTER_API_KEY` em .env

```python
# app/ai/model_router.py

TASK_MODEL_MAP = {
    # tarefa leve — categorizacao, resumo simples
    "categorize_transaction":  "google/gemini-flash-1.5",
    "summarize_month":         "meta-llama/llama-3.1-8b-instruct",

    # tarefa media — analise de padrao, sugestao de economia
    "spending_analysis":       "anthropic/claude-haiku",
    "savings_suggestion":      "openai/gpt-4o-mini",
    "cashflow_forecast":       "anthropic/claude-haiku",

    # tarefa avancada — conselho personalizado, analise de risco
    "financial_advisor":       "anthropic/claude-sonnet-4-5",
    "fraud_semantic_analysis": "anthropic/claude-sonnet-4-5",
    "security_audit":          "openai/gpt-4o",

    # tarefa critica — decisoes que envolvem compliance
    "compliance_check":        "anthropic/claude-sonnet-4-5",
}

TOKEN_BUDGET_PER_USER_PER_DAY = 50_000   # guardrail de custo
```

Endpoint base: `https://openrouter.ai/api/v1/chat/completions`
Header obrigatorio: `HTTP-Referer: https://biocodetechpay.com.br`

### 2.4 Context Builder — Contexto do Usuario para o LLM

O context builder transforma dados do banco em contexto estruturado, **sem expor dados sensiveis ao modelo**:

```python
# app/ai/context_builder.py

def build_financial_context(user: User, db: Session, days: int = 90) -> dict:
    """
    Retorna contexto anonimizado e estruturado.
    NUNCA inclui: CPF, senha, token, chave PIX completa, numero de cartao.
    """
    txs = get_recent_transactions(user.id, db, days)
    return {
        "current_balance": user.balance,
        "account_age_days": (datetime.now() - user.created_at).days,
        "monthly_income_avg": calculate_avg_income(txs),
        "monthly_expense_avg": calculate_avg_expense(txs),
        "top_spending_categories": categorize_expenses(txs),
        "recurring_payments": detect_recurring(txs),
        "cashflow_trend": calculate_trend(txs),       # positivo / negativo / estavel
        "last_30d_tx_count": len([t for t in txs if t.recent]),
        "large_single_payments": [t.value for t in txs if t.value > 500],
        # identificadores mascarados — apenas para referencia interna
        "masked_user_ref": hashlib.sha256(user.id.encode()).hexdigest()[:16]
    }
```

### 2.5 Endpoints da API de AI

```
POST /ai/chat
  Body: { "message": "quanto gastei com alimentacao esse mes?" }
  Auth: Bearer token obrigatorio
  Response: { "reply": "...", "model_used": "...", "tokens_used": 342, "cached": false }
  Rate limit: 30 requests/hora por usuario free, 200/hora premium

GET /ai/insights
  Response: lista de insights proativos gerados em background (job diario)
  Exemplo: ["Voce gastou 40% mais com delivery em fevereiro vs janeiro",
             "Saldo previsto para dia 25: R$-120 — considere uma transferencia"]

GET /ai/score
  Response: {
    "score": 72,
    "grade": "B",
    "breakdown": {
      "balance_stability": 80,
      "expense_diversity": 65,
      "income_regularity": 70,
      "savings_rate": 73
    },
    "top_action": "Reduza gastos com delivery em R$80 para atingir score A"
  }

POST /ai/security/analyze
  Admin only — analisa transacoes recentes em busca de padroes suspeitos
  Body: { "user_id": "...", "window_hours": 24 }
  Response: { "risk_level": "low|medium|high", "findings": [...], "recommended_action": "..." }

GET /ai/security/report
  Admin only — relatorio geral de saude de seguranca do sistema
```

### 2.6 Score de Saude Financeira — Formula

$$\text{Score} = 0.25 \cdot S_{\text{estabilidade}} + 0.25 \cdot S_{\text{renda}} + 0.25 \cdot S_{\text{diversidade}} + 0.25 \cdot S_{\text{poupanca}}$$

Onde cada componente e normalizado de 0 a 100:

- **Estabilidade de saldo**: razao entre saldo minimo e saldo medio nos ultimos 90 dias
- **Regularidade de renda**: coeficiente de variacao das entradas mensais (menor CV = maior score)
- **Diversidade de gastos**: entropia de Shannon das categorias de despesa
- **Taxa de poupanca**: (entradas - saidas) / entradas * 100

### 2.7 Motor Antifraude Semantico

Complementa as regras do `app/antifraude/rules.py` com analise comportamental:

```python
# Sinais de fraude que regras fixas nao detectam:

SEMANTIC_FRAUD_SIGNALS = [
    "primeiro_pix_valor_atipico",    # primeiro PIX de conta nova com valor > media do segmento
    "mudanca_abrupta_horario",       # usuario sempre opera 9h-18h, de repente 3h da manha
    "sequencia_valores_redondos",    # 5 PIX de R$100 em 10 minutos — smurfing
    "novo_beneficiario_alto_valor",  # primeiro contato com destinatario, valor > R$1.000
    "velocidade_anormal",            # 10 transacoes em 2 minutos
    "geolocalizacao_inconsistente",  # IP Brasil, depois IP externo em 5 minutos (futuro)
]
```

O LLM recebe o contexto anonimizado + sequencia de transacoes e responde com JSON estruturado:
```json
{
  "risk_level": "high",
  "signals_detected": ["velocidade_anormal", "novo_beneficiario_alto_valor"],
  "confidence": 0.91,
  "recommended_action": "block_and_notify",
  "explanation": "5 PIX em 3 minutos para destinatario nunca contactado anteriormente, valor total R$2.400"
}
```

### 2.8 Seguranca Autonoma — Cobertura OWASP

O modulo `security_scanner.py` executa as seguintes verificacoes em job agendado (diario):

**A1 - Broken Access Control**
- Verifica se endpoints administrativos retornam 403 para tokens de usuario comum
- Verifica se dados de usuario A nao sao acessiveis com token de usuario B

**A2 - Cryptographic Failures**
- Verifica algoritmo do JWT (HS256 aceitavel para MVP, RS256 recomendado para producao)
- Verifica se senhas estao hasheadas com bcrypt/argon2 (nunca MD5/SHA1)
- Verifica presenca de HTTPS em todas as rotas expostas

**A3 - Injection**
- Verifica se queries usam parametros bound (SQLAlchemy ORM — ja protegido)
- Verifica inputs de usuario que chegam em queries de busca

**A5 - Security Misconfiguration**
- Verifica headers HTTP de seguranca presentes em todas as respostas:
  - `Strict-Transport-Security`
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Content-Security-Policy`
- Verifica se DEBUG=False em producao
- Verifica se SECRET_KEY nao e o valor default

**A7 - Identification and Authentication Failures**
- Verifica rate limiting nos endpoints `/auth/login` e `/auth/register`
- Verifica expiracao do JWT (max recomendado: 15 min access + 7 dias refresh)
- Verifica se tentativas de login com senha errada sao limitadas

**A10 - SSRF**
- Verifica se URLs externas aceitas pelo sistema sao validadas contra lista de dominios permitidos

### 2.9 Guardrails do LLM

Todo output do LLM passa por validacao antes de chegar ao usuario:

```python
# app/ai/guardrails.py

BLOCKED_PATTERNS = [
    r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}",    # CPF
    r"\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}",  # numero de cartao
    r"(?i)(senha|password|token|secret)",          # dados sensiveis
    r"(?i)(comprar acoes|investir em|aplicar em)", # conselho de investimento nao regulado
]

MAX_RESPONSE_TOKENS = 800          # limite de output por resposta
REQUIRE_JSON_OUTPUT = True         # para endpoints de analise (nao chat)
```

### 2.10 Jobs em Background (APScheduler ou Celery futuro)

```python
# Executados pelo scheduler — nao bloqueiam requisicoes de usuario

@scheduler.scheduled_job("cron", hour=6)
async def generate_daily_insights():
    # Para cada usuario Premium, gera insights do dia anterior
    # Armazena em tabela ai_insights para GET /ai/insights

@scheduler.scheduled_job("cron", hour="*/4")
async def run_fraud_scan():
    # Analisa transacoes das ultimas 4 horas em busca de padroes suspeitos
    # Gera alertas em tabela ai_security_alerts

@scheduler.scheduled_job("cron", day_of_week="mon", hour=3)
async def run_security_audit():
    # Varredura semanal de endpoints e configuracoes
    # Gera relatorio em ai_security_reports
```

---

## Parte 3 — Cronograma de Implementacao

### Sprint 1 (1 semana) — Taxas Basicas
- [ ] Criar `app/fees/policy.py` com FeePolicy e FeeBreakdown
- [ ] Criar migracao SQL: `account_type` em users + tabela `fee_ledger`
- [ ] Integrar calculo de taxa no PIX externo (Routing 2 do router.py)
- [ ] Endpoint `GET /fees/preview?type=pix_external&value=100`
- [ ] Endpoint `GET /fees/history` (historico de taxas do usuario)
- [ ] Testes: cobranca correta, isencao admin, atomicidade com transacao

### Sprint 2 (1 semana) — Modulo AI Base
- [ ] Criar `app/ai/model_router.py` com OpenRouter client
- [ ] Criar `app/ai/context_builder.py` com anonimizacao de dados
- [ ] Implementar `POST /ai/chat` com modelo basico
- [ ] Implementar guardrails de output (dados sensiveis + limite de tokens)
- [ ] Token budget por usuario por dia (Redis counter)
- [ ] Testes: sem vazamento de CPF/senha em respostas, rate limit funcional

### Sprint 3 (1 semana) — Score e Insights
- [ ] Implementar `GET /ai/score` com formula documentada na secao 2.6
- [ ] Job agendado de geracao de insights diarios
- [ ] `GET /ai/insights` — lista de insights do usuario
- [ ] Testes: score calculado corretamente para diferentes perfis simulados

### Sprint 4 (1 semana) — Seguranca e Antifraude AI
- [ ] Implementar `security_scanner.py` com checks OWASP A1-A10
- [ ] Integrar analise semantica de fraude no fluxo do antifraude existente
- [ ] `GET /ai/security/report` para admin
- [ ] Security headers middleware (HSTS, X-Frame-Options, CSP)
- [ ] Testes: scanner detecta configuracoes inseguras em ambiente de teste

### Sprint 5 (1 semana) — Linguagem Natural para Operacoes
- [ ] Parser de intencao: "paga R$30 pro Joao" -> POST /pix/transferir
- [ ] Confirmacao antes de executar qualquer operacao financeira via NL
- [ ] Historico de conversas por usuario (contexto entre sessoes)
- [ ] Testes: intencoes reconhecidas corretamente, sem execucao sem confirmacao

---

## Parte 4 — Variaveis de Ambiente Necessarias

```
# OpenRouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_REFERER=https://biocodetechpay.com.br

# Fee Policy
EXEMPT_ACCOUNT_EMAILS=biocodetechnology@gmail.com
ADMIN_REVENUE_ACCOUNT_ID=<user_id_da_conta_admin>

# AI Budget Controls
AI_MAX_TOKENS_PER_USER_PER_DAY=50000
AI_MONTHLY_BUDGET_USD=50.00
AI_FALLBACK_MODEL=meta-llama/llama-3.1-8b-instruct

# Security Scanner
SECURITY_SCAN_ENABLED=true
SECURITY_ALERT_WEBHOOK_URL=<webhook_slack_ou_email>
```

---

## Parte 5 — Dependencias a Adicionar em requirements.txt

```
# AI
openai>=1.0.0             # OpenRouter usa client-compativel com OpenAI SDK
tiktoken>=0.7.0           # contagem de tokens antes de enviar (controle de custo)
apscheduler>=3.10.0       # jobs em background (insights, scan de fraude)

# Seguranca
slowapi>=0.1.9            # rate limiting (ja pode estar instalado)
python-jose[cryptography] # JWT com RS256 (upgrade do HS256)

# Analytics
scikit-learn>=1.4.0       # Isolation Forest para anomaly detection
numpy>=1.26.0             # computacao numerica para score e previsao
```

---

## Referencias Tecnicas

- OpenRouter API: `https://openrouter.ai/docs`
- BCB Resolucao PIX Gratuidade PF: Resolucao BCB n. 1/2020
- OWASP Top 10 2021: `https://owasp.org/Top10/`
- LGPD Art. 46: medidas tecnicas de seguranca para dados financeiros
- PCI DSS v4.0 Requirement 6.4: protecao de aplicacoes web publicas
