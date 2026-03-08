"""
Factory for payment gateway adapter instantiation.
Implements Dependency Injection pattern following SOLID principles.
"""
from typing import Optional
from app.ports.payment_gateway_port import PaymentGatewayPort
from app.adapters.asaas_adapter import AsaasAdapter
from app.core.config import settings
from app.core.logger import logger


_gateway_instance: Optional[PaymentGatewayPort] = None


def get_payment_gateway() -> Optional[PaymentGatewayPort]:
    """
    Returns singleton instance of payment gateway adapter.

    Returns:
        PaymentGatewayPort implementation (AsaasAdapter) or None if not configured

    Raises:
        ValueError: If ASAAS_API_KEY is invalid
    """
    global _gateway_instance

    if _gateway_instance is not None:
        return _gateway_instance

    if not settings.ASAAS_API_KEY:
        logger.warning(
            "ASAAS_API_KEY not configured. PIX real integration disabled. "
            "Set ASAAS_API_KEY environment variable to enable."
        )
        return None

    try:
        _gateway_instance = AsaasAdapter(
            api_key=settings.ASAAS_API_KEY,
            use_sandbox=settings.ASAAS_USE_SANDBOX
        )
        logger.info("Payment gateway adapter initialized successfully")
        return _gateway_instance
    except Exception as e:
        logger.error(f"Failed to initialize payment gateway: {str(e)}")
        raise


def reset_gateway_instance():
    """
    Resets singleton instance (for testing purposes).
    """
    global _gateway_instance
    _gateway_instance = None
