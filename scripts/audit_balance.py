"""
Audita a consistencia entre saldo registrado em users.balance
e a soma das transacoes confirmadas no banco.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.auth.models import User
from app.pix.models import PixTransaction, TransactionType, PixStatus
from app.cards.models import CreditCard  # resolve relationship before query
from app.boleto.models import BoletoTransaction
from app.parcelamento.models import InstallmentSimulation
from sqlalchemy import func
from datetime import datetime, timezone, timedelta

db = SessionLocal()

users = db.query(User).all()

print("=== USUARIOS E SALDOS ===")
for u in users:
    print(f"  {u.email} | saldo={u.balance:.2f} | limite={u.credit_limit:.2f}")

print()
print("=== TRANSACOES PIX (ultimas 20) ===")
txs = db.query(PixTransaction).order_by(PixTransaction.created_at.desc()).limit(20).all()
for t in txs:
    tp = t.type.value if hasattr(t.type, "value") else str(t.type)
    st = t.status.value if hasattr(t.status, "value") else str(t.status)
    print(f"  [{tp}] [{st}] val={t.value:.2f} user={t.user_id} id={str(t.id)[:24]}")

print()
print("=== AUDITORIA DE SALDO POR USUARIO ===")
divergencias = 0
for u in users:
    # Debitos efetivos: ENVIADO com status CONFIRMADO ou PROCESSANDO
    sent = db.query(func.sum(PixTransaction.value)).filter(
        PixTransaction.user_id == u.id,
        PixTransaction.type == TransactionType.SENT,
        PixTransaction.status.in_([PixStatus.CONFIRMED, PixStatus.PROCESSING])
    ).scalar() or 0.0

    received = db.query(func.sum(PixTransaction.value)).filter(
        PixTransaction.user_id == u.id,
        PixTransaction.type == TransactionType.RECEIVED,
        PixTransaction.status == PixStatus.CONFIRMED
    ).scalar() or 0.0

    initial_balance = 0.0  # User.balance default=0.00 (app/auth/models.py)
    expected = round(initial_balance + received - sent, 2)
    real = round(u.balance, 2)
    diff = round(real - expected, 2)
    flag = "  <-- DIVERGENCIA" if abs(diff) > 0.01 else ""
    if abs(diff) > 0.01:
        divergencias += 1
    print(f"  {u.email}: saldo_db={real:.2f} | esperado={expected:.2f} | diff={diff:.2f}{flag}")

print()
print("=== CONTAGEM POR STATUS ===")
statuses = db.query(PixTransaction.status, func.count(PixTransaction.id)).group_by(PixTransaction.status).all()
for st, cnt in statuses:
    print(f"  {st}: {cnt} transacao(oes)")

print()
print("=== TRANSACOES PRESAS (CRIADO) ===")
presas = db.query(PixTransaction).filter(
    PixTransaction.status == PixStatus.CREATED
).order_by(PixTransaction.created_at.desc()).limit(10).all()
if not presas:
    print("  Nenhuma transacao CRIADO encontrada.")
else:
    for t in presas:
        tp = t.type.value if hasattr(t.type, "value") else str(t.type)
        print(f"  [{tp}] val={t.value:.2f} user={t.user_id} id={str(t.id)[:30]} criado={t.created_at}")

print()
if divergencias == 0:
    print("RESULTADO: sem divergencias detectadas.")
else:
    print(f"RESULTADO: {divergencias} divergencia(s) encontrada(s). Revisar manualmente.")

db.close()
