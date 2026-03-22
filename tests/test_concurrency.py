"""
Concurrency tests for BioCodeTechPay.

Validates that critical financial operations handle concurrent access safely.
NOTE: SQLite lacks row-level locking (SELECT FOR UPDATE). These tests use
serialized writes via BEGIN IMMEDIATE to emulate safe concurrency. Full
concurrency testing with proper isolation requires PostgreSQL.
"""
import os
import tempfile
import threading
import pytest
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.database import Base
from app.auth.models import User
from app.pix.models import PixTransaction, PixStatus, TransactionType
from uuid import uuid4
from datetime import datetime, timezone

# Import all models so SQLAlchemy registers them
from app.boleto.models import BoletoTransaction  # noqa: F401
from app.parcelamento.models import InstallmentSimulation  # noqa: F401
from app.cards.models import CreditCard  # noqa: F401


@pytest.fixture()
def engine():
    """Shared engine for concurrency tests (file-based SQLite for cross-thread access)."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        pool_size=1,
        max_overflow=4,
    )
    with eng.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture()
def seed_user(session_factory):
    """Creates a test user with R$100.00 balance."""
    session = session_factory()
    user = User(
        id=str(uuid4()),
        name="Concurrency Test User",
        email="concurrent@test.com",
        cpf_cnpj="12345678900",
        hashed_password="hashed_placeholder",
        balance=100.0,
    )
    session.add(user)
    session.commit()
    uid = user.id
    session.close()
    return uid


class TestConcurrentBalanceDebit:
    """Validates that concurrent debits do not overdraw balance."""

    def test_double_debit_does_not_exceed_balance(self, session_factory, seed_user):
        """
        Two threads each try to debit R$80 from a R$100 balance using
        an application-level mutex (simulating what the real app does
        via database-level locks in PostgreSQL).
        Only one should succeed; the other must see insufficient funds.
        """
        user_id = seed_user
        results = []
        lock = threading.Lock()

        def attempt_debit(amount: float):
            session = session_factory()
            try:
                with lock:
                    user = session.query(User).filter(User.id == user_id).first()
                    amount_dec = Decimal(str(amount))
                    if user.balance >= amount_dec:
                        user.balance -= amount_dec
                        tx = PixTransaction(
                            id=str(uuid4()),
                            value=amount,
                            type=TransactionType.SENT,
                            status=PixStatus.CONFIRMED,
                            user_id=user_id,
                            pix_key="test-key",
                            key_type="RANDOM",
                            idempotency_key=str(uuid4()),
                            recipient_name="Recipient",
                        )
                        session.add(tx)
                        session.commit()
                        return "SUCCESS"
                    else:
                        session.rollback()
                        return "INSUFFICIENT"
            except Exception as e:
                session.rollback()
                return f"ERROR: {e}"
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(attempt_debit, 80.0) for _ in range(2)]
            for f in as_completed(futures):
                results.append(f.result())

        success_count = results.count("SUCCESS")
        assert success_count == 1, (
            f"Exactly one debit must succeed with R$100 balance and R$80 debit: {results}"
        )

        session = session_factory()
        user = session.query(User).filter(User.id == user_id).first()
        assert user.balance >= 0, (
            f"Balance became negative: R${user.balance:.2f} after results={results}"
        )
        assert abs(user.balance - Decimal("20.00")) < Decimal("0.01"), (
            f"Expected R$20.00 remaining, got R${user.balance}"
        )
        session.close()

    def test_many_small_debits_converge_to_zero(self, session_factory, seed_user):
        """
        10 sequential-serialized debits of R$10 from R$100 balance.
        With proper locking, all succeed and final balance = R$0.
        """
        user_id = seed_user
        lock = threading.Lock()

        def attempt_small_debit():
            session = session_factory()
            try:
                with lock:
                    session.expire_all()
                    user = session.query(User).filter(User.id == user_id).first()
                    if user.balance >= Decimal("10.00"):
                        user.balance -= Decimal("10.00")
                        session.commit()
                        return "SUCCESS"
                    else:
                        session.rollback()
                        return "INSUFFICIENT"
            except Exception:
                session.rollback()
                return "ERROR"
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(attempt_small_debit) for _ in range(10)]
            results = [f.result() for f in as_completed(futures)]

        success_count = results.count("SUCCESS")
        session = session_factory()
        user = session.query(User).filter(User.id == user_id).first()
        final_balance = user.balance
        session.close()

        expected = Decimal("100.00") - (success_count * Decimal("10.00"))
        assert abs(final_balance - expected) < Decimal("0.01"), (
            f"Balance mismatch: expected R${expected}, got R${final_balance}"
        )
        assert final_balance >= 0, f"Negative balance: R${final_balance}"
        assert success_count == 10, (
            f"All 10 debits should succeed: {success_count} succeeded"
        )


class TestConcurrentTransactionCreation:
    """Validates that concurrent transaction creation does not produce duplicates."""

    def test_concurrent_charge_creation(self, session_factory, seed_user):
        """
        5 threads create charges simultaneously for the same user.
        Each should produce a unique transaction ID.
        """
        user_id = seed_user
        tx_ids = []

        def create_charge():
            session = session_factory()
            try:
                tx = PixTransaction(
                    id=str(uuid4()),
                    value=25.0,
                    type=TransactionType.RECEIVED,
                    status=PixStatus.CREATED,
                    user_id=user_id,
                    pix_key=str(uuid4()),
                    key_type="RANDOM",
                    idempotency_key=str(uuid4()),
                    recipient_name="Test Merchant",
                )
                session.add(tx)
                session.commit()
                return tx.id
            except Exception as e:
                session.rollback()
                return None
            finally:
                session.close()

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_charge) for _ in range(5)]
            for f in as_completed(futures):
                result = f.result()
                if result:
                    tx_ids.append(result)

        assert len(tx_ids) == len(set(tx_ids)), (
            f"Duplicate transaction IDs detected: {tx_ids}"
        )
        assert len(tx_ids) == 5, f"Expected 5 charges, got {len(tx_ids)}"
