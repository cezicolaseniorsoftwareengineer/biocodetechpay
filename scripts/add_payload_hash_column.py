"""
Migration: add payload_hash column to transacoes_pix table.

Purpose:
  Server-side deduplication by EMV content. Prevents the same user from paying
  the same QR code / Pix Copia e Cola twice, regardless of what idempotency
  header the frontend sends.

Schema change:
  ALTER TABLE transacoes_pix ADD COLUMN IF NOT EXISTS payload_hash VARCHAR(64);
  CREATE UNIQUE INDEX IF NOT EXISTS uix_pix_user_payload_hash ON transacoes_pix (user_id, payload_hash)
    WHERE payload_hash IS NOT NULL;

Idempotent: safe to run multiple times against the same database.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.database import engine
from app.core.logger import logger


def migrate():
    steps = [
        (
            "add payload_hash column",
            "ALTER TABLE transacoes_pix ADD COLUMN IF NOT EXISTS payload_hash VARCHAR(64);",
        ),
        (
            "create partial unique index uix_pix_user_payload_hash",
            """CREATE UNIQUE INDEX IF NOT EXISTS uix_pix_user_payload_hash
            ON transacoes_pix (user_id, payload_hash)
            WHERE payload_hash IS NOT NULL;""",
        ),
    ]

    try:
        with engine.connect() as conn:
            for label, sql in steps:
                logger.info(f"Migration step: {label}")
                conn.execute(text(sql))
                logger.info(f"Migration step OK: {label}")
            conn.commit()
        logger.info("Migration complete: payload_hash added to transacoes_pix")
        print("Migration OK: payload_hash column + unique index created on transacoes_pix")
        return True
    except Exception as exc:
        logger.error(f"Migration failed: {exc}")
        print(f"Migration FAILED: {exc}")
        return False


def rollback():
    steps = [
        ("drop index", "DROP INDEX IF EXISTS uix_pix_user_payload_hash;"),
        ("drop column", "ALTER TABLE transacoes_pix DROP COLUMN IF EXISTS payload_hash;"),
    ]

    try:
        with engine.connect() as conn:
            for label, sql in steps:
                logger.warning(f"Rollback step: {label}")
                conn.execute(text(sql))
            conn.commit()
        print("Rollback OK: payload_hash column and index removed")
        return True
    except Exception as exc:
        print(f"Rollback FAILED: {exc}")
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        print("Running rollback...")
        rollback()
    else:
        print("Running migration: add payload_hash to transacoes_pix...")
        migrate()
