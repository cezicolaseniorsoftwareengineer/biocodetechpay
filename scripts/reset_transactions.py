"""
Hard reset of all PIX and Boleto transactions in the database.
Use before go-live to ensure the ledger matches the real Asaas account state.

Usage:
    python scripts/reset_transactions.py

Safety:
    - Prompts for confirmation before deleting
    - Resets user balances to R$ 0.00 (matching a fresh real Asaas account)
    - Does NOT delete user accounts or authentication data
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.database import SessionLocal
from app.pix.models import PixTransaction
from app.boleto.models import BoletoTransaction
from app.auth.models import User


def main():
    print("=== RESET DE TRANSACOES ===")
    print("Este script apaga TODAS as transacoes PIX e Boleto do banco de dados.")
    print("Os dados de usuario (login, CPF, email) serao preservados.")
    print()

    confirm = input("Digite CONFIRMAR para prosseguir: ").strip()
    if confirm != "CONFIRMAR":
        print("Operacao cancelada.")
        sys.exit(0)

    db = SessionLocal()
    try:
        pix_count = db.query(PixTransaction).count()
        boleto_count = db.query(BoletoTransaction).count()
        user_count = db.query(User).count()

        print(f"\nEncontrado:")
        print(f"  PIX transactions: {pix_count}")
        print(f"  Boleto transactions: {boleto_count}")
        print(f"  Users: {user_count}")
        print()

        # Delete all PIX transactions
        db.query(PixTransaction).delete(synchronize_session=False)
        print(f"  {pix_count} PIX transactions deletadas.")

        # Delete all Boleto transactions
        db.query(BoletoTransaction).delete(synchronize_session=False)
        print(f"  {boleto_count} Boleto transactions deletadas.")

        # Reset all user balances and credit limits to zero
        updated = db.query(User).update(
            {"balance": 0.0, "credit_limit": 0.0},
            synchronize_session=False
        )
        print(f"  {updated} usuarios com saldo zerado.")

        db.commit()
        print("\nReset concluido com sucesso.")
        print("O banco esta limpo e pronto para operar com dados reais.")

    except Exception as e:
        db.rollback()
        print(f"\nERRO durante reset: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
