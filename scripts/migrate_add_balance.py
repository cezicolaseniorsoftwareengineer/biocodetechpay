"""
Migration script to add balance field to users table.
Idempotent: safe to run multiple times.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.database import engine
from app.core.logger import logger


def migrate_add_balance():
    """
    Adds balance (saldo) column to users table if not exists.
    Sets default value of 0.00 for existing users.
    """
    migration_sql = """
    ALTER TABLE users ADD COLUMN IF NOT EXISTS saldo FLOAT DEFAULT 0.00 NOT NULL;
    """

    try:
        with engine.connect() as conn:
            logger.info("Starting migration: add_balance_to_users")
            conn.execute(text(migration_sql))
            conn.commit()
            logger.info("Migration completed successfully: balance field added")
            print("✓ Migration successful: balance (saldo) column added to users table")
            return True
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        print(f"✗ Migration failed: {str(e)}")
        return False


def rollback_migration():
    """
    Removes balance column if migration needs to be reverted.
    WARNING: This will delete all balance data.
    """
    rollback_sql = """
    ALTER TABLE users DROP COLUMN IF EXISTS saldo;
    """

    try:
        with engine.connect() as conn:
            logger.warning("Starting rollback: remove_balance_from_users")
            conn.execute(text(rollback_sql))
            conn.commit()
            logger.warning("Rollback completed: balance field removed")
            print("✓ Rollback successful: balance column removed from users table")
            return True
    except Exception as e:
        logger.error(f"Rollback failed: {str(e)}")
        print(f"✗ Rollback failed: {str(e)}")
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        print("Running rollback migration...")
        rollback_migration()
    else:
        print("Running migration to add balance field...")
        migrate_add_balance()
