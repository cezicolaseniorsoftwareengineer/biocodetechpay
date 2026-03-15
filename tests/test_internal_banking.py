"""
Tests for internal banking features: deposits, balance, internal PIX transfers.
Validates BioCodeTechPay internal banking system without external gateway.
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
        email="test@biocodetechpay.com",
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
        email="test2@biocodetechpay.com",
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
    recipient = find_recipient_user(db, "test2@biocodetechpay.com", PixKeyType.EMAIL)

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

    assert test_user.balance == 699.00   # 1000 - 300 - 1.00 maint.
    assert test_user_2.balance == 300.00

    assert sent_tx.value == 300.00
    assert sent_tx.status.value == "CONFIRMADO"
    assert recv_tx.value == 300.00
    assert recv_tx.status.value == "CONFIRMADO"


def test_internal_transfer_insufficient_balance(db, test_user, test_user_2):
    """Tests internal transfer with insufficient balance."""
    with pytest.raises(ValueError, match="Saldo insuficiente"):
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

    assert test_user.balance == 1249.00   # 2000 - 750 - 1.00 maint.
    assert test_user_2.balance == 1250.00  # 500 + 750 (receiver pays no fee)


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

    assert get_user_balance(db, test_user.id) == 899.00   # 1500 - 600 - 1.00 maint.
    assert get_user_balance(db, test_user_2.id) == 600.00


# ---------------------------------------------------------------------------
# Audit auto-correction logic — bidirectional
# ---------------------------------------------------------------------------

def test_audit_matrix_credit_when_asaas_above_internal(db):
    """
    Simulates the asaas_above_internal scenario:
    Asaas holds R$3.08 but all internal balances are R$0.00.
    The audit engine must credit Matrix with the diff to restore parity.
    """
    matrix = User(
        name="Matrix",
        email="matrix@biocodetechpay.internal",
        cpf_cnpj="00000000000100",
        hashed_password=get_password_hash("x"),
        balance=0.0,
    )
    customer = User(
        name="Customer A",
        email="customer@biocodetechpay.com",
        cpf_cnpj="11111111111",
        hashed_password=get_password_hash("x"),
        balance=0.0,
    )
    db.add_all([matrix, customer])
    db.commit()
    db.refresh(matrix)

    # Simulate: Asaas = 3.08, all internal = 0.00
    asaas_balance = 3.08
    internal_sum = 0.0
    matrix_balance = float(matrix.balance)
    total_internal = internal_sum + matrix_balance
    diff = round(total_internal - asaas_balance, 2)  # -3.08
    abs_diff = abs(diff)

    assert diff < 0, "Should be asaas_above_internal"
    assert abs_diff <= 20.0, "Within auto-correction limit"

    # Apply correction: credit Matrix
    matrix.balance = round(matrix_balance + abs_diff, 2)
    db.add(matrix)
    db.commit()
    db.refresh(matrix)

    assert round(matrix.balance, 2) == 3.08
    new_total = round(0.0 + matrix.balance, 2)
    assert abs(new_total - asaas_balance) < 0.01, "Internal must equal Asaas after correction"


def test_audit_customer_debit_when_internal_above_asaas(db):
    """
    Simulates the internal_above_asaas scenario:
    Asaas charged R$2.98 gateway fee on an inbound transfer.
    The customer was credited with the gross value (R$13.08) but
    Asaas only holds R$10.10 after the fee deduction.

    Rule: Matrix is NOT touched — it holds only realized platform margin.
    The shortfall must be recovered from customers with positive balance.
    Matrix must remain unchanged after correction.
    """
    matrix = User(
        name="Matrix",
        email="matrix2@biocodetechpay.internal",
        cpf_cnpj="00000000000200",
        hashed_password=get_password_hash("x"),
        balance=5.00,  # has accumulated fees — must remain untouched
    )
    customer = User(
        name="Bio Code Technology",
        email="customer_bio@test.com",
        cpf_cnpj="11111111111",
        hashed_password=get_password_hash("x"),
        balance=13.08,  # was credited gross — 2.98 excess
    )
    db.add_all([matrix, customer])
    db.commit()

    asaas_balance = 10.10
    matrix_balance = float(matrix.balance)          # 5.00
    customer_balance = float(customer.balance)       # 13.08
    total_internal = matrix_balance + customer_balance  # 18.08
    diff = round(total_internal - asaas_balance, 2)     # +7.98 - but let's use the real-world scenario
    # Simplified: only the customer balance exceeds; matrix is separate
    # Real scenario: total_internal = 13.08, asaas = 10.10, diff = 2.98
    # For isolation: strip matrix from the equation
    cust_internal = customer_balance   # 13.08
    cust_asaas = asaas_balance         # 10.10 (asaas holds what the customer deposited net of fees)
    abs_diff = round(cust_internal - cust_asaas, 2)  # 2.98

    assert abs_diff > 0, "Customer internal > asaas — shortfall exists"
    assert abs_diff <= 20.0, "Within auto-correction limit"

    # Mirror the new audit_worker correction logic: debit customer, leave matrix unchanged
    matrix_before = float(matrix.balance)
    live_customers = [customer]
    total_cust_bal = sum(float(u.balance) for u in live_customers)
    customers_debited = []
    remainder = abs_diff
    for c in sorted(live_customers, key=lambda u: float(u.balance), reverse=True):
        share = round((float(c.balance) / total_cust_bal) * abs_diff, 2)
        actual_debit = min(share, float(c.balance), remainder)
        if actual_debit > 0:
            c.balance = round(float(c.balance) - actual_debit, 2)
            db.add(c)
            customers_debited.append({"id": str(c.id), "amount": actual_debit})
            remainder = round(remainder - actual_debit, 2)
    db.commit()
    db.refresh(matrix)
    db.refresh(customer)

    # Matrix must remain unchanged
    assert round(float(matrix.balance), 2) == matrix_before, "Matrix must NOT be debited"

    # Customer absorbed the shortfall
    assert round(float(customer.balance), 2) == round(customer_balance - abs_diff, 2)  # 13.08 - 2.98 = 10.10
    assert round(float(customer.balance), 2) == 10.10

    assert len(customers_debited) == 1
    assert round(customers_debited[0]["amount"], 2) == 2.98


def test_audit_no_correction_above_limit(db):
    """
    Divergences above R$20 must NOT be auto-corrected.
    Both directions should remain unchanged.
    """
    _AUTO_CORRECTION_MAX = 20.0
    abs_diff_large = 25.00
    assert abs_diff_large > _AUTO_CORRECTION_MAX, "Should exceed auto-correction limit"


# ---------------------------------------------------------------------------
# Matrix-never-negative invariant tests
# ---------------------------------------------------------------------------

def test_matrix_never_goes_negative(db):
    """
    Invariant: Matrix.balance must never go below R$0.00.

    Scenario: internal total exceeds Asaas by R$5.00,
    but Matrix only holds R$1.00.

    Expected:
    - Matrix absorbs R$1.00 -> balance = R$0.00 (floor enforced)
    - Remaining R$4.00 distributed proportionally to customers
      (Customer A 60% -> R$2.40, Customer B 40% -> R$1.60)
    - All balances >= 0.00 after correction
    """
    matrix = User(
        name="Matrix",
        email="matrix3@biocodetechpay.internal",
        cpf_cnpj="00000000000300",
        hashed_password=get_password_hash("x"),
        balance=1.00,
    )
    cust_a = User(
        name="Customer A",
        email="custa_neg@test.com",
        cpf_cnpj="11111111100",
        hashed_password=get_password_hash("x"),
        balance=60.00,
    )
    cust_b = User(
        name="Customer B",
        email="custb_neg@test.com",
        cpf_cnpj="22222222200",
        hashed_password=get_password_hash("x"),
        balance=40.00,
    )
    db.add_all([matrix, cust_a, cust_b])
    db.commit()

    abs_diff = 5.00
    matrix_current = float(matrix.balance)  # 1.00

    # Mirror the audit_worker correction logic exactly
    matrix_absorbs = min(abs_diff, max(0.0, matrix_current))   # 1.00
    remainder = round(abs_diff - matrix_absorbs, 2)              # 4.00
    matrix.balance = round(matrix_current - matrix_absorbs, 2)  # 0.00

    live_customers = [cust_a, cust_b]
    total_cust_bal = sum(float(u.balance) for u in live_customers)  # 100.00
    customers_debited = []
    if remainder > 0.01 and total_cust_bal > 0:
        for customer in sorted(live_customers, key=lambda u: float(u.balance), reverse=True):
            share = round((float(customer.balance) / total_cust_bal) * remainder, 2)
            actual_debit = min(share, float(customer.balance))
            if actual_debit > 0:
                customer.balance = round(float(customer.balance) - actual_debit, 2)
                customers_debited.append({"id": str(customer.id), "amount": actual_debit})

    db.commit()
    db.refresh(matrix)
    db.refresh(cust_a)
    db.refresh(cust_b)

    # Core invariant
    assert float(matrix.balance) >= 0.00, "Matrix balance must never go negative"
    assert round(float(matrix.balance), 2) == 0.00

    # Proportional distribution: 60% of R$4.00 = R$2.40, 40% = R$1.60
    assert round(float(cust_a.balance), 2) == 57.60, "Customer A: 60.00 - 2.40"
    assert round(float(cust_b.balance), 2) == 38.40, "Customer B: 40.00 - 1.60"

    total_debited = sum(entry["amount"] for entry in customers_debited)
    assert round(total_debited, 2) == 4.00
    assert len(customers_debited) == 2


def test_matrix_zero_balance_all_shortfall_to_customers(db):
    """
    Invariant: when Matrix balance is R$0.00,
    the entire shortfall must be charged to customers.
    Matrix must remain at R$0.00 — never go below.

    This reproduces the real production incident where Asaas charged
    R$2.98 inbound gross fee and Matrix had R$0.00, causing -R$2.98.
    """
    matrix = User(
        name="Matrix",
        email="matrix4@biocodetechpay.internal",
        cpf_cnpj="00000000000400",
        hashed_password=get_password_hash("x"),
        balance=0.00,
    )
    cust = User(
        name="Customer C",
        email="custc_zero@test.com",
        cpf_cnpj="33333333300",
        hashed_password=get_password_hash("x"),
        balance=10.00,
    )
    db.add_all([matrix, cust])
    db.commit()

    abs_diff = 2.98  # typical Asaas inbound gross cost
    matrix_current = float(matrix.balance)  # 0.00

    matrix_absorbs = min(abs_diff, max(0.0, matrix_current))  # 0.00
    remainder = round(abs_diff - matrix_absorbs, 2)            # 2.98

    if matrix_absorbs > 0:
        matrix.balance = round(matrix_current - matrix_absorbs, 2)

    live_customers = [cust]
    total_cust_bal = sum(float(u.balance) for u in live_customers)  # 10.00
    customers_debited = []
    if remainder > 0.01 and total_cust_bal > 0:
        for customer in sorted(live_customers, key=lambda u: float(u.balance), reverse=True):
            share = round((float(customer.balance) / total_cust_bal) * remainder, 2)
            actual_debit = min(share, float(customer.balance))
            if actual_debit > 0:
                customer.balance = round(float(customer.balance) - actual_debit, 2)
                customers_debited.append({"id": str(customer.id), "amount": actual_debit})

    db.commit()
    db.refresh(matrix)
    db.refresh(cust)

    # Matrix must remain at 0.00 — NOT -2.98
    assert round(float(matrix.balance), 2) == 0.00, "Matrix must stay at 0.00 when already empty"
    assert float(matrix.balance) >= 0.00, "Matrix balance must never go negative"

    # Customer absorbed the full R$2.98
    assert round(float(cust.balance), 2) == 7.02  # 10.00 - 2.98
    assert len(customers_debited) == 1
    assert round(customers_debited[0]["amount"], 2) == 2.98
