"""
Tests for internal banking features: deposits, balance, internal PIX transfers.
Validates PayvoraX internal banking system without external gateway.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base
from app.auth.models import User
from app.auth.service import deposit_funds, get_user_balance, get_password_hash
from app.pix.internal_transfer import find_recipient_user, execute_internal_transfer
from app.pix.schemas import PixKeyType


@pytest.fixture(scope="function")
def db():
    """Creates in-memory database for tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def test_user(db):
    """Creates a test user."""
    user = User(
        name="Test User",
        email="test@payvorax.com",
        cpf_cnpj="12345678901",
        hashed_password=get_password_hash("senha123"),
        balance=0.0,
        credit_limit=10000.0
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_user_2(db):
    """Creates a second test user for transfer tests."""
    user = User(
        name="Test User 2",
        email="test2@payvorax.com",
        cpf_cnpj="98765432100",
        hashed_password=get_password_hash("senha456"),
        balance=0.0,
        credit_limit=5000.0
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_user_has_balance_field(test_user):
    """Validates that User model has balance field."""
    assert hasattr(test_user, 'balance')
    assert test_user.balance == 0.0


def test_deposit_funds(db, test_user):
    """Tests deposit functionality."""
    result = deposit_funds(
        db=db,
        user_id=test_user.id,
        amount=500.00,
        description="Test deposit"
    )

    assert result["amount"] == 500.00
    assert result["previous_balance"] == 0.0
    assert result["new_balance"] == 500.00
    assert result["user_id"] == test_user.id

    db.refresh(test_user)
    assert test_user.balance == 500.00


def test_deposit_invalid_amount(db, test_user):
    """Tests deposit with invalid amount."""
    with pytest.raises(ValueError, match="Deposit amount must be positive"):
        deposit_funds(db, test_user.id, -100.00)

    with pytest.raises(ValueError, match="Deposit amount must be positive"):
        deposit_funds(db, test_user.id, 0.00)


def test_deposit_exceeds_limit(db, test_user):
    """Tests deposit exceeding maximum allowed."""
    with pytest.raises(ValueError, match="Deposit amount exceeds limit"):
        deposit_funds(db, test_user.id, 2000000.00)


def test_get_user_balance(db, test_user):
    """Tests balance retrieval."""
    deposit_funds(db, test_user.id, 1000.00)

    balance = get_user_balance(db, test_user.id)
    assert balance == 1000.00


def test_find_recipient_by_cpf(db, test_user, test_user_2):
    """Tests finding recipient user by CPF."""
    recipient = find_recipient_user(db, "98765432100", PixKeyType.CPF)

    assert recipient is not None
    assert recipient.id == test_user_2.id
    assert recipient.name == "Test User 2"


def test_find_recipient_by_email(db, test_user, test_user_2):
    """Tests finding recipient user by email."""
    recipient = find_recipient_user(db, "test2@payvorax.com", PixKeyType.EMAIL)

    assert recipient is not None
    assert recipient.id == test_user_2.id


def test_find_recipient_not_found(db):
    """Tests finding non-existent recipient."""
    recipient = find_recipient_user(db, "99999999999", PixKeyType.CPF)
    assert recipient is None


def test_internal_transfer_success(db, test_user, test_user_2):
    """Tests successful internal PIX transfer."""
    deposit_funds(db, test_user.id, 1000.00)

    sent_tx, recv_tx = execute_internal_transfer(
        db=db,
        sender=test_user,
        recipient=test_user_2,
        amount=300.00,
        pix_key="98765432100",
        key_type="CPF",
        description="Internal transfer test",
        idempotency_key="test-idempotency-123",
        correlation_id="test-correlation-456"
    )

    db.commit()
    db.refresh(test_user)
    db.refresh(test_user_2)

    assert test_user.balance == 700.00
    assert test_user_2.balance == 300.00

    assert sent_tx.value == 300.00
    assert sent_tx.status.value == "CONFIRMADO"
    assert recv_tx.value == 300.00
    assert recv_tx.status.value == "CONFIRMADO"


def test_internal_transfer_insufficient_balance(db, test_user, test_user_2):
    """Tests internal transfer with insufficient balance."""
    with pytest.raises(ValueError, match="Insufficient balance"):
        execute_internal_transfer(
            db=db,
            sender=test_user,
            recipient=test_user_2,
            amount=500.00,
            pix_key="98765432100",
            key_type="CPF",
            description="Should fail",
            idempotency_key="test-fail-123",
            correlation_id="test-fail-456"
        )


def test_internal_transfer_updates_balance(db, test_user, test_user_2):
    """Tests that internal transfer correctly updates both balances."""
    deposit_funds(db, test_user.id, 2000.00)
    deposit_funds(db, test_user_2.id, 500.00)

    execute_internal_transfer(
        db=db,
        sender=test_user,
        recipient=test_user_2,
        amount=750.00,
        pix_key="98765432100",
        key_type="CPF",
        description="Balance update test",
        idempotency_key="test-balance-123",
        correlation_id="test-balance-456"
    )

    db.commit()
    db.refresh(test_user)
    db.refresh(test_user_2)

    assert test_user.balance == 1250.00
    assert test_user_2.balance == 1250.00


def test_multiple_deposits_accumulate(db, test_user):
    """Tests that multiple deposits accumulate correctly."""
    deposit_funds(db, test_user.id, 100.00)
    deposit_funds(db, test_user.id, 200.00)
    deposit_funds(db, test_user.id, 300.00)

    db.refresh(test_user)
    assert test_user.balance == 600.00


def test_deposit_and_transfer_flow(db, test_user, test_user_2):
    """Tests complete flow: deposit -> internal transfer -> balance check."""
    deposit_funds(db, test_user.id, 1500.00)

    assert get_user_balance(db, test_user.id) == 1500.00
    assert get_user_balance(db, test_user_2.id) == 0.00

    execute_internal_transfer(
        db=db,
        sender=test_user,
        recipient=test_user_2,
        amount=600.00,
        pix_key="98765432100",
        key_type="CPF",
        description="Full flow test",
        idempotency_key="test-flow-123",
        correlation_id="test-flow-456"
    )

    db.commit()

    assert get_user_balance(db, test_user.id) == 900.00
    assert get_user_balance(db, test_user_2.id) == 600.00
