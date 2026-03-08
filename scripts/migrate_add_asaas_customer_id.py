"""
Database migration: Add asaas_customer_id to users table.

This script adds support for Asaas customer ID storage in the User model.
Required for PIX charge creation via Asaas BaaS API.

SAFETY:
- Uses ALTER TABLE ADD COLUMN IF NOT EXISTS (idempotent)
- Non-destructive operation
- Nullable column (no data loss risk)
- Indexed for performance

Run with: python scripts/migrate_add_asaas_customer_id.py
"""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.database import engine
from app.core.logger import logger


def migrate():
    """Apply migration to add asaas_customer_id column."""

    migration_sql = """
    -- Add asaas_customer_id column to users table (idempotent)
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS asaas_customer_id VARCHAR(100);

    -- Create index for performance (idempotent)
    CREATE INDEX IF NOT EXISTS idx_users_asaas_customer_id
    ON users(asaas_customer_id);
    """

    try:
        with engine.connect() as conn:
            # Execute migration
            conn.execute(text(migration_sql))
            conn.commit()

            logger.info("Migration completed successfully: asaas_customer_id column added to users table")
            print("✓ Migration successful: asaas_customer_id column added")
            print("✓ Index created: idx_users_asaas_customer_id")

            # Verify migration
            result = conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'users' AND column_name = 'asaas_customer_id'
            """))

            row = result.fetchone()
            if row:
                print(f"✓ Verification: Column exists - {row[0]} ({row[1]}, nullable={row[2]})")
            else:
                print("⚠ Warning: Column verification failed (may not be PostgreSQL)")

    except Exception as e:
        logger.error(f"Migration failed: {str(e)}", exc_info=True)
        print(f"✗ Migration failed: {str(e)}")
        raise


def rollback():
    """Rollback migration (remove asaas_customer_id column)."""

    rollback_sql = """
    -- Drop index
    DROP INDEX IF EXISTS idx_users_asaas_customer_id;

    -- Drop column
    ALTER TABLE users DROP COLUMN IF EXISTS asaas_customer_id;
    """

    try:
        with engine.connect() as conn:
            conn.execute(text(rollback_sql))
            conn.commit()

            logger.info("Rollback completed: asaas_customer_id column removed")
            print("✓ Rollback successful: asaas_customer_id column removed")

    except Exception as e:
        logger.error(f"Rollback failed: {str(e)}", exc_info=True)
        print(f"✗ Rollback failed: {str(e)}")
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate users table for Asaas integration")
    parser.add_argument("--rollback", action="store_true", help="Rollback migration")
    args = parser.parse_args()

    if args.rollback:
        print("Rolling back migration...")
        rollback()
    else:
        print("Applying migration...")
        migrate()
