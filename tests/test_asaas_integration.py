"""
Integration tests for Asaas PIX payment gateway.
Tests real API integration with production credentials.

WARNING: These tests make real API calls to Asaas production environment.
Only run when ASAAS_API_KEY is configured.
"""
import pytest
from decimal import Decimal
from uuid import uuid4
from sqlalchemy.orm import Session
from app.adapters.gateway_factory import get_payment_gateway
from app.pix.service import (
    create_pix_charge_with_qrcode,
    ensure_asaas_customer,
    sync_pix_charge_status
)
from app.core.database import get_db
from app.auth.models import User
from app.core.config import settings


@pytest.fixture
def test_user(db: Session):
    """Creates a test user for integration tests."""
    user = User(
        id=str(uuid4()),
        name="Test User Asaas",
        cpf_cnpj="12345678901",  # Test CPF
        email=f"test_{uuid4()}@biocodetechpay.com",
        hashed_password="hashed",
        credit_limit=10000.00
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user
    # Cleanup
    db.delete(user)
    db.commit()


@pytest.mark.skipif(
    not settings.ASAAS_INTEGRATION_TESTS,
    reason="Asaas real-money integration tests disabled (set ASAAS_INTEGRATION_TESTS=true to enable). "
           "Requires valid CPF/CNPJ and production Asaas credentials."
)
class TestAsaasProductionIntegration:
    """
    Integration tests for Asaas production environment.

    Skipped if:
    - ASAAS_API_KEY not configured
    - ASAAS_USE_SANDBOX=true (not production)
    """

    def test_payment_gateway_initialization(self):
        """Test that payment gateway is properly initialized."""
        gateway = get_payment_gateway()
        assert gateway is not None
        assert gateway.api_key == settings.ASAAS_API_KEY
        assert gateway.base_url == gateway.BASE_URL_PRODUCTION

    def test_create_asaas_customer(self, db: Session, test_user: User):
        """Test customer creation on Asaas."""
        customer_id = ensure_asaas_customer(db, test_user.id)

        assert customer_id is not None
        assert len(customer_id) > 0

        # Verify customer ID was stored in user model
        db.refresh(test_user)
        assert test_user.asaas_customer_id == customer_id

    def test_create_pix_charge(self, db: Session, test_user: User):
        """Test PIX charge creation with QR Code."""
        idempotency_key = f"test-charge-{uuid4()}"
        correlation_id = str(uuid4())

        pix_charge = create_pix_charge_with_qrcode(
            db=db,
            value=10.50,
            description="Test PIX charge - Asaas integration",
            user_id=test_user.id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id
        )

        assert pix_charge is not None
        assert pix_charge.id is not None  # Asaas payment ID
        assert pix_charge.value == 10.50
        assert pix_charge.pix_key is not None  # QR Code copy-paste
        assert len(pix_charge.pix_key) > 50  # QR Code should be long EMV string
        assert pix_charge.status.value == "CRIADO"
        assert pix_charge.type.value == "RECEBIDO"

    def test_sync_charge_status(self, db: Session, test_user: User):
        """Test synchronization of charge status from Asaas."""
        # First create a charge
        idempotency_key = f"test-sync-{uuid4()}"
        correlation_id = str(uuid4())

        pix_charge = create_pix_charge_with_qrcode(
            db=db,
            value=15.75,
            description="Test charge status sync",
            user_id=test_user.id,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id
        )

        # Sync status from Asaas
        updated_pix = sync_pix_charge_status(db, pix_charge.id)

        assert updated_pix is not None
        assert updated_pix.id == pix_charge.id
        # Status should still be PENDING since we just created it
        assert updated_pix.status.value in ["CRIADO", "PROCESSANDO"]


@pytest.mark.skipif(
    not settings.ASAAS_API_KEY,
    reason="Asaas API key not configured"
)
class TestAsaasAdapterMethods:
    """
    Unit tests for Asaas adapter methods.
    Can run in sandbox or production.
    """

    def test_create_pix_charge_via_adapter(self):
        """Test PIX charge creation directly via adapter."""
        gateway = get_payment_gateway()
        assert gateway is not None

        # This test requires a real customer ID
        # Skipping execution to avoid real charge creation
        pytest.skip("Requires real customer ID from database")

    def test_get_charge_status_not_found(self):
        """Test querying status of non-existent charge."""
        gateway = get_payment_gateway()
        assert gateway is not None

        fake_charge_id = "invalid-charge-id-12345"

        with pytest.raises(Exception):  # Should raise HTTPError 404
            gateway.get_charge_status(fake_charge_id)


def test_asaas_config_loaded():
    """Test that Asaas configuration is properly loaded."""
    assert settings.ASAAS_API_KEY is not None
    assert len(settings.ASAAS_API_KEY) > 20
    assert settings.ASAAS_API_KEY.startswith("$aact_")
    assert settings.ASAAS_USE_SANDBOX == False  # Production mode
