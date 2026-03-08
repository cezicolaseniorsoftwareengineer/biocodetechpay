"""
Script de limpeza: remove transacoes fictícias acumuladas pela auto-confirmacao de QR local.
Criadas por: POST /pix/receber/confirmar com charge gerado localmente (nao via Asaas).

Marcadores de transacoes fake:
  - pix_key = 'DYNAMIC_QR_CODE'   (fallback de simulacao local)
  - pix_key = 'SIMULACAO_QR_CODE' (legado de testes antigos)

Transacoes Asaas reais:
  - pix_key contem payload EMV (comeca com '0002') ou ID de pagamento Asaas

Execucao: python scripts/clean_fake_transactions.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine, Base
from app.pix.models import PixTransaction, PixStatus, TransactionType
from app.auth.models import User
from sqlalchemy import func

db = SessionLocal()

try:
    # Diagnostico antes da limpeza
    user = db.query(User).first()
    if not user:
        print("ERRO: nenhum usuario encontrado no banco.")
        sys.exit(1)

    print(f"\nUsuario: {user.name}")
    print(f"Balance atual (user.balance): R$ {user.balance:.2f}")

    total_txns = db.query(func.count(PixTransaction.id)).filter(
        PixTransaction.user_id == user.id
    ).scalar()

    fake_keys = ["DYNAMIC_QR_CODE", "SIMULACAO_QR_CODE"]

    fake_count = db.query(func.count(PixTransaction.id)).filter(
        PixTransaction.user_id == user.id,
        PixTransaction.pix_key.in_(fake_keys)
    ).scalar()

    real_count = total_txns - fake_count

    print(f"\nTotal de transacoes no DB: {total_txns}")
    print(f"  Fake (QR local):          {fake_count}")
    print(f"  Reais:                    {real_count}")

    if fake_count == 0:
        print("\nNenhuma transacao fake encontrada. Nada a limpar.")
        sys.exit(0)

    print(f"\nAgindo: deletando {fake_count} transacoes fake...")

    deleted = db.query(PixTransaction).filter(
        PixTransaction.user_id == user.id,
        PixTransaction.pix_key.in_(fake_keys)
    ).delete(synchronize_session=False)

    db.commit()
    print(f"Deletadas: {deleted} transacoes fake.")

    # Balanco final
    remaining = db.query(func.count(PixTransaction.id)).filter(
        PixTransaction.user_id == user.id
    ).scalar()

    print(f"\nTransacoes restantes no DB: {remaining}")
    print(f"user.balance (intocado):    R$ {user.balance:.2f}")
    print("\nLimpeza concluida. O extrato agora reflete apenas transacoes reais.")

except Exception as e:
    db.rollback()
    print(f"\nERRO durante limpeza: {e}")
    raise
finally:
    db.close()
