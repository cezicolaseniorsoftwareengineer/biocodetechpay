"""
Unit tests for Asaas adapter configuration and initialization.
Tests that do not require database or external API calls.
"""
import pytest
from app.core.config import settings
from app.adapters.gateway_factory import get_payment_gateway
from app.adapters.asaas_adapter import AsaasAdapter


class TestAsaasConfiguration:
    """Test Asaas configuration and initialization without external dependencies."""

    def test_asaas_api_key_configured(self):
        """Verify that Asaas API key is properly configured."""
        assert settings.ASAAS_API_KEY is not None, "ASAAS_API_KEY must be set in .env"
        assert len(settings.ASAAS_API_KEY) > 20, "ASAAS_API_KEY appears to be invalid"
        assert settings.ASAAS_API_KEY.startswith("$aact_"), "ASAAS_API_KEY must start with $aact_"

    def test_asaas_production_mode(self):
        """Verify that Asaas is configured for production."""
        assert settings.ASAAS_USE_SANDBOX == False, "ASAAS_USE_SANDBOX must be False for production"

    def test_asaas_adapter_initialization(self):
        """Test that AsaasAdapter can be initialized with valid API key."""
        api_key = settings.ASAAS_API_KEY
        adapter = AsaasAdapter(api_key=api_key, use_sandbox=settings.ASAAS_USE_SANDBOX)

        assert adapter is not None
        assert adapter.api_key == api_key
        assert adapter.base_url == AsaasAdapter.BASE_URL_PRODUCTION
        assert adapter.client is not None

    def test_gateway_factory_returns_asaas_adapter(self):
        """Test that payment gateway factory returns AsaasAdapter instance."""
        gateway = get_payment_gateway()

        assert gateway is not None
        assert isinstance(gateway, AsaasAdapter)
        assert gateway.api_key == settings.ASAAS_API_KEY

    def test_asaas_adapter_base_url_production(self):
        """Verify that production base URL is correct."""
        adapter = AsaasAdapter(api_key=settings.ASAAS_API_KEY, use_sandbox=False)
        assert adapter.base_url == "https://api.asaas.com/v3"

    def test_asaas_adapter_headers(self):
        """Verify that HTTP client has correct headers."""
        adapter = AsaasAdapter(api_key=settings.ASAAS_API_KEY, use_sandbox=False)

        headers = adapter.client.headers
        assert "access_token" in headers
        assert headers["access_token"] == settings.ASAAS_API_KEY
        assert headers["Content-Type"] == "application/json"
        assert "User-Agent" in headers

    def test_asaas_adapter_timeout(self):
        """Verify that HTTP client has appropriate timeout."""
        adapter = AsaasAdapter(api_key=settings.ASAAS_API_KEY, use_sandbox=False)
        assert adapter.client.timeout.read == 15.0
        assert adapter.client.timeout.connect == 15.0


class TestAsaasAdapterMethods:
    """Test that Asaas adapter has all required methods."""

    def test_adapter_has_create_pix_charge(self):
        """Verify create_pix_charge method exists."""
        gateway = get_payment_gateway()
        assert hasattr(gateway, 'create_pix_charge')
        assert callable(gateway.create_pix_charge)

    def test_adapter_has_create_pix_payment(self):
        """Verify create_pix_payment method exists."""
        gateway = get_payment_gateway()
        assert hasattr(gateway, 'create_pix_payment')
        assert callable(gateway.create_pix_payment)

    def test_adapter_has_get_charge_status(self):
        """Verify get_charge_status method exists."""
        gateway = get_payment_gateway()
        assert hasattr(gateway, 'get_charge_status')
        assert callable(gateway.get_charge_status)

    def test_adapter_has_get_payment_status(self):
        """Verify get_payment_status method exists."""
        gateway = get_payment_gateway()
        assert hasattr(gateway, 'get_payment_status')
        assert callable(gateway.get_payment_status)

    def test_adapter_has_cancel_charge(self):
        """Verify cancel_charge method exists."""
        gateway = get_payment_gateway()
        assert hasattr(gateway, 'cancel_charge')
        assert callable(gateway.cancel_charge)

    def test_adapter_has_create_customer(self):
        """Verify create_customer method exists."""
        gateway = get_payment_gateway()
        assert hasattr(gateway, 'create_customer')
        assert callable(gateway.create_customer)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
