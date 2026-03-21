"""
Migration: Float -> Numeric(15,2)

Converts all financial columns from FLOAT (IEEE 754) to NUMERIC(15,2)
to prevent cumulative rounding drift in monetary operations.

Affected tables:
  - users.saldo, users.limite_credito
  - transacoes_pix.valor, transacoes_pix.taxa_valor
  - transacoes_boleto.valor, transacoes_boleto.taxa_valor
  - credit_cards.limit

Idempotent: re-running is safe (ALTER TYPE on already-NUMERIC columns is a no-op).

Usage:
  python scripts/migrate_float_to_numeric.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import SessionLocal


ALTERATIONS = [
    "ALTER TABLE users ALTER COLUMN saldo TYPE NUMERIC(15,2) USING saldo::NUMERIC(15,2)",
    "ALTER TABLE users ALTER COLUMN limite_credito TYPE NUMERIC(15,2) USING limite_credito::NUMERIC(15,2)",
    "ALTER TABLE transacoes_pix ALTER COLUMN valor TYPE NUMERIC(15,2) USING valor::NUMERIC(15,2)",
    "ALTER TABLE transacoes_pix ALTER COLUMN taxa_valor TYPE NUMERIC(15,2) USING taxa_valor::NUMERIC(15,2)",
    "ALTER TABLE transacoes_boleto ALTER COLUMN valor TYPE NUMERIC(15,2) USING valor::NUMERIC(15,2)",
    "ALTER TABLE transacoes_boleto ALTER COLUMN taxa_valor TYPE NUMERIC(15,2) USING taxa_valor::NUMERIC(15,2)",
    "ALTER TABLE credit_cards ALTER COLUMN \"limit\" TYPE NUMERIC(15,2) USING \"limit\"::NUMERIC(15,2)",
]


def main():
    db = SessionLocal()
    try:
        for stmt in ALTERATIONS:
            table_col = stmt.split("ALTER COLUMN")[1].split("TYPE")[0].strip()
            table_name = stmt.split("ALTER TABLE")[1].split("ALTER")[0].strip()
            try:
                db.execute(text(stmt))
                print(f"  OK  {table_name}.{table_col} -> NUMERIC(15,2)")
            except Exception as e:
                err_msg = str(e)
                if "does not exist" in err_msg:
                    print(f"  SKIP {table_name}.{table_col} (table/column not found)")
                else:
                    print(f"  WARN {table_name}.{table_col}: {err_msg}")
        db.commit()
        print("\nMigration complete.")
    except Exception as e:
        db.rollback()
        print(f"\nMigration failed: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
