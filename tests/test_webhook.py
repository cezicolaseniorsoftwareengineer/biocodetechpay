"""
Webhook handler tests — security, idempotency, and edge cases.

Covers:
- Token validation (hmac.compare_digest timing-safe comparison)
- Invalid/missing token rejection
- TRANSFER_DONE status update
- TRANSFER_FAILED balance refund
- Duplicate payload idempotency
- Withdrawal validation webhook
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from app.main import app
from app.core.database import get_db
from app.auth.models import User
from app.pix.models import PixTransaction, PixStatus, TransactionType
from app.core.config import settings as _app_settings
from datetime import datetime, timezone

_TEST_WEBHOOK_TOKEN = "wh-test-secure-token-2024"
_TEST_WITHDRAWAL_TOKEN = "wd-test-secure-token-2024"

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_dependency_overrides():
    saved = dict(app.dependency_overrides)
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def _make_user(user_id: str = "user-wh-001", balance: float = 100.0) -> User:
    return User(
        id=user_id,
        name="Webhook Test User",
        cpf_cnpj="12345678901",
        credit_limit=500.0,
        balance=balance,
    )


def _make_tx(
    tx_id: str = "tx-wh-001",
    value: float = 25.0,
    status: PixStatus = PixStatus.CREATED,
    tx_type: TransactionType = TransactionType.SENT,
    user_id: str = "user-wh-001",
    fee_amount: float = 0.0,
) -> PixTransaction:
    return PixTransaction(
        id=tx_id,
        value=value,
        status=status,
        user_id=user_id,
        type=tx_type,
        pix_key="destination-key",
        key_type="ALEATORIA",
        description="Webhook test tx",
        fee_amount=fee_amount,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestWebhookTokenSecurity:
    """Validates that webhook authentication is enforced correctly."""

    def test_wrong_token_rejected(self, monkeypatch):
        """Webhook with incorrect token must be rejected — no balance mutation."""
        monkeypatch.setattr(_app_settings, "ASAAS_WEBHOOK_TOKEN", _TEST_WEBHOOK_TOKEN)

        payload = {
            "event": "PAYMENT_RECEIVED",
            "payment": {"id": "pay-fake-001", "value": 999.99},
        }

        response = client.post(
            "/pix/webhook/asaas",
            json=payload,
            headers={"asaas-access-token": "wrong-token-attempt"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("received") is False

    def test_missing_token_header_rejected(self, monkeypatch):
        """Webhook without token header must be rejected."""
        monkeypatch.setattr(_app_settings, "ASAAS_WEBHOOK_TOKEN", _TEST_WEBHOOK_TOKEN)

        payload = {
            "event": "PAYMENT_RECEIVED",
            "payment": {"id": "pay-no-header-001", "value": 100.0},
        }

        response = client.post("/pix/webhook/asaas", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data.get("received") is False

    def test_unconfigured_token_rejects_all(self, monkeypatch):
        """When ASAAS_WEBHOOK_TOKEN is None, ALL webhooks must be rejected."""
        monkeypatch.setattr(_app_settings, "ASAAS_WEBHOOK_TOKEN", None)

        payload = {
            "event": "PAYMENT_RECEIVED",
            "payment": {"id": "pay-inject-001", "value": 50000.0},
        }

        response = client.post("/pix/webhook/asaas", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data.get("received") is False
        assert data.get("action") == "rejected"


class TestWebhookTransferEvents:
    """Tests TRANSFER_DONE and TRANSFER_FAILED webhook processing."""

    def test_transfer_done_updates_status(self, monkeypatch):
        """TRANSFER_DONE must update transaction to CONFIRMED."""
        monkeypatch.setattr(_app_settings, "ASAAS_WEBHOOK_TOKEN", _TEST_WEBHOOK_TOKEN)

        mock_db = MagicMock()
        tx = _make_tx(status=PixStatus.CREATED, tx_type=TransactionType.SENT)
        mock_db.query.return_value.filter.return_value.first.return_value = tx

        app.dependency_overrides[get_db] = lambda: mock_db

        payload = {
            "event": "TRANSFER_DONE",
            "payment": {"id": "tx-wh-001", "value": 25.0},
        }

        response = client.post(
            "/pix/webhook/asaas",
            json=payload,
            headers={"asaas-access-token": _TEST_WEBHOOK_TOKEN},
        )

        assert response.status_code == 200
        assert tx.status == PixStatus.CONFIRMED

    def test_transfer_failed_refunds_balance(self, monkeypatch):
        """TRANSFER_FAILED must restore balance + fee to user."""
        monkeypatch.setattr(_app_settings, "ASAAS_WEBHOOK_TOKEN", _TEST_WEBHOOK_TOKEN)

        mock_db = MagicMock()
        user = _make_user(balance=50.0)
        fee_amount = 4.0
        tx = _make_tx(
            status=PixStatus.CREATED,
            tx_type=TransactionType.SENT,
            value=25.0,
            fee_amount=fee_amount,
        )

        # First query returns PixTransaction, second returns User, third returns matrix user
        matrix_user = _make_user(user_id="matrix-wh-001", balance=100.0)
        mock_db.query.return_value.filter.return_value.first.side_effect = [tx, user, matrix_user]

        app.dependency_overrides[get_db] = lambda: mock_db

        payload = {
            "event": "TRANSFER_FAILED",
            "payment": {"id": "tx-wh-001", "value": 25.0},
        }

        response = client.post(
            "/pix/webhook/asaas",
            json=payload,
            headers={"asaas-access-token": _TEST_WEBHOOK_TOKEN},
        )

        assert response.status_code == 200
        assert tx.status in (PixStatus.FAILED, PixStatus.CANCELED)
        # Balance must be restored: original 50 + value 25 + fee 4 = 79
        expected_balance = 50.0 + 25.0 + fee_amount
        assert abs(float(user.balance) - expected_balance) < 0.01, (
            f"Expected balance R${expected_balance:.2f} after refund, got R${float(user.balance):.2f}"
        )


class TestWebhookIdempotency:
    """Validates duplicate webhook handling."""

    def test_duplicate_payment_received_is_noop(self, monkeypatch):
        """Second PAYMENT_RECEIVED for same charge must not double-credit."""
        monkeypatch.setattr(_app_settings, "ASAAS_WEBHOOK_TOKEN", _TEST_WEBHOOK_TOKEN)

        mock_db = MagicMock()
        tx = _make_tx(
            tx_id="pay-dup-001",
            status=PixStatus.CONFIRMED,
            tx_type=TransactionType.RECEIVED,
            value=100.0,
        )
        mock_db.query.return_value.filter.return_value.first.return_value = tx

        app.dependency_overrides[get_db] = lambda: mock_db

        payload = {
            "event": "PAYMENT_RECEIVED",
            "payment": {"id": "pay-dup-001", "value": 100.0},
        }

        response = client.post(
            "/pix/webhook/asaas",
            json=payload,
            headers={"asaas-access-token": _TEST_WEBHOOK_TOKEN},
        )

        assert response.status_code == 200
        assert response.json().get("action") == "already_confirmed"


class TestWithdrawalValidation:
    """Tests the withdrawal validation webhook endpoint."""

    def test_approved_with_valid_token(self, monkeypatch):
        """Valid token must return APPROVED."""
        monkeypatch.setattr(
            _app_settings, "ASAAS_WITHDRAWAL_VALIDATION_TOKEN", _TEST_WITHDRAWAL_TOKEN
        )

        payload = {
            "type": "TRANSFER",
            "transfer": {"id": "wd-001", "value": 100.0},
        }

        response = client.post(
            "/pix/webhook/asaas/validacao-saque",
            json=payload,
            headers={"asaas-access-token": _TEST_WITHDRAWAL_TOKEN},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "APPROVED"

    def test_refused_with_wrong_token(self, monkeypatch):
        """Wrong token must return REFUSED."""
        monkeypatch.setattr(
            _app_settings, "ASAAS_WITHDRAWAL_VALIDATION_TOKEN", _TEST_WITHDRAWAL_TOKEN
        )

        payload = {
            "type": "TRANSFER",
            "transfer": {"id": "wd-002", "value": 50.0},
        }

        response = client.post(
            "/pix/webhook/asaas/validacao-saque",
            json=payload,
            headers={"asaas-access-token": "wrong-token"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "REFUSED"

    def test_refused_when_token_not_configured(self, monkeypatch):
        """Security invariant: when no token configured, ALL withdrawals REFUSED (fail-closed)."""
        monkeypatch.setattr(
            _app_settings, "ASAAS_WITHDRAWAL_VALIDATION_TOKEN", None
        )

        payload = {
            "type": "PIX",
            "transfer": {"id": "wd-003", "value": 200.0},
        }

        response = client.post(
            "/pix/webhook/asaas/validacao-saque",
            json=payload,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "REFUSED"
