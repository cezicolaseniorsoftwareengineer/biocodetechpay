"""Corrige saldo do admin: debita R$ 4.48 que foi creditado indevidamente.

Estado antes da execucao:
  biocodetechnology@gmail.com  R$ 8.96  (incorreto)
Estado esperado apos execucao:
  biocodetechnology@gmail.com  R$ 4.48  (correto — alinhado com Asaas R$ 44.48)

Causa raiz: webhook Asaas sem ASAAS_WEBHOOK_TOKEN configurado aceitava qualquer
requisicao nao autenticada. Uma simulacao/teste creditou R$ 4.48 na conta admin
sem transacao real Asaas correspondente. A correcao foi aplicada e o webhook
foi endurecido (rejeita se token nao configurado).

Execute UMA vez. Verifique saldo antes e depois.
"""
import os, sys
os.environ["BIO_CODE_TECH_PAY_ALLOWED_START"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import text  # noqa
from app.core.database import SessionLocal
import app.cards.models    # noqa: registers CreditCard
import app.boleto.models   # noqa: registers BoletoTransaction
import app.pix.models      # noqa: registers PixTransaction
from app.auth.models import User

ADMIN_EMAIL = "biocodetechnology@gmail.com"
DEBIT_AMOUNT = Decimal("4.48")
TWO = Decimal("0.01")

db = SessionLocal()
try:
    admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
    if not admin:
        print(f"ERRO: conta {ADMIN_EMAIL} nao encontrada.")
        sys.exit(1)

    current = Decimal(str(admin.balance)).quantize(TWO, rounding=ROUND_HALF_UP)
    print(f"Saldo atual: R$ {current}")

    if current < DEBIT_AMOUNT:
        print(f"ABORT: saldo R$ {current} e inferior ao debito R$ {DEBIT_AMOUNT}. Nada feito.")
        sys.exit(1)

    expected_after = (current - DEBIT_AMOUNT).quantize(TWO, rounding=ROUND_HALF_UP)
    if abs(expected_after - Decimal("4.48")) > Decimal("0.01"):
        print(f"AVISO: resultado esperado R$ {expected_after} difere de R$ 4.48. Verificar antes de continuar.")
        resp = input("Continuar mesmo assim? (s/N): ").strip().lower()
        if resp != "s":
            print("Cancelado.")
            sys.exit(0)

    admin.balance = float(expected_after)
    db.add(admin)
    db.commit()
    db.refresh(admin)

    final = Decimal(str(admin.balance)).quantize(TWO, rounding=ROUND_HALF_UP)
    print(f"Saldo corrigido: R$ {final}")
    print("Correcao aplicada com sucesso.")
finally:
    db.close()
