"""
Migration: Create the ledger_entries table for double-entry auditable ledger.
Supports PIX Payment Consistency Hardening (P3.5).
Idempotent: will not fail if the table already exists.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import inspect
from app.core.database import engine
from app.pix.models import LedgerEntry


def migrate():
    inspector = inspect(engine)
    existing = inspector.get_table_names()

    if "ledger_entries" in existing:
        print("[OK] Table 'ledger_entries' already exists. Skipping.")
        return

    LedgerEntry.__table__.create(bind=engine)
    print("[OK] Table 'ledger_entries' created successfully.")


if __name__ == "__main__":
    migrate()
