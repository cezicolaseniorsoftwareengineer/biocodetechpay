"""
Corrects balance for SENT+FAILED PIX transactions where the amount
was deducted at dispatch time but never restored (pre-fix state).

Run once after deploying the TRANSFER_FAILED webhook balance-restore fix.
Going forward, the webhook handles this automatically.

Usage:
    python scripts/fix_failed_transfer_balance.py [--dry-run]
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.cards.models import CreditCard  # required: resolves User.cards mapper relationship
from app.pix.models import PixTransaction, TransactionType
from app.pix.schemas import PixStatus
from app.auth.models import User

DRY_RUN = "--dry-run" in sys.argv


def main():
    db = SessionLocal()
    try:
        # Find all SENT+FAILED transactions — these had balance deducted but not restored
        failed_sent = (
            db.query(PixTransaction)
            .filter(
                PixTransaction.type == TransactionType.SENT,
                PixTransaction.status == PixStatus.FAILED,
            )
            .all()
        )

        if not failed_sent:
            print("Nenhuma transacao SENT+FAILED encontrada. Nada a corrigir.")
            return

        print(f"Encontradas {len(failed_sent)} transacao(oes) SENT+FAILED:")
        print()

        total_restored = 0.0

        for tx in failed_sent:
            user = db.query(User).filter(User.id == tx.user_id).first()
            if not user:
                print(f"  [SKIP] tx={tx.id}: usuario {tx.user_id} nao encontrado")
                continue

            print(f"  tx={tx.id}")
            print(f"    usuario: {user.name} ({user.id})")
            print(f"    valor: R$ {tx.value:.2f}")
            print(f"    saldo atual: R$ {user.balance:.2f}")
            print(f"    saldo apos correcao: R$ {user.balance + tx.value:.2f}")

            if not DRY_RUN:
                user.balance += tx.value
                db.add(user)
                total_restored += tx.value

            print()

        if DRY_RUN:
            print("[DRY-RUN] Nenhuma alteracao aplicada. Rode sem --dry-run para corrigir.")
        else:
            db.commit()
            print(f"Correcao aplicada. Total restaurado: R$ {total_restored:.2f}")

    except Exception as e:
        db.rollback()
        print(f"Erro: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
