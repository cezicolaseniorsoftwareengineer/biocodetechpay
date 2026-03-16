"""
Database migration: Add asaas_wallet_id to users table.

Adds walletId storage to support segregated Asaas subconta routing per user.
Each registered user will have an individual Asaas sub-account walletId after
this migration, enabling per-user wallet isolation under the parent platform account.

SAFETY:
- Uses ALTER TABLE ADD COLUMN IF NOT EXISTS (idempotent)
- Non-destructive: nullable column, zero data loss risk
- Indexed for foreign-key-style lookups (walletId -> user)

Run with: python scripts/migrate_add_asaas_wallet_id.py
After migration, run: python scripts/backfill_asaas_wallets.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.database import engine
from app.core.logger import logger


def migrate() -> None:
    """Apply migration to add asaas_wallet_id column (idempotent)."""

    migration_sql = """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS asaas_wallet_id VARCHAR(36);

    CREATE INDEX IF NOT EXISTS idx_users_asaas_wallet_id
    ON users(asaas_wallet_id);
    """

    try:
        with engine.connect() as conn:
            conn.execute(text(migration_sql))
            conn.commit()

            logger.info("Migration completed: asaas_wallet_id added to users table")
            print("Migration successful: asaas_wallet_id column added to users")
            print("Index created: idx_users_asaas_wallet_id")

            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'asaas_wallet_id'
            """))
            row = result.fetchone()
            if row:
                print(f"Verified: {row[0]} ({row[1]}, nullable={row[2]})")
            else:
                print("Note: column verification not available (non-PostgreSQL engine)")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    migrate()
