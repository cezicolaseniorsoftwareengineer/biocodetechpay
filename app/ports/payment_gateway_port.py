"""
Payment Gateway Port (Interface).
Defines contract for PIX payment providers following Hexagonal Architecture.
All payment gateway adapters must implement this protocol.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime


class PaymentGatewayPort(ABC):
    """
    Abstract interface for payment gateway integrations.
    Implementations: AsaasAdapter, BradescoAdapter, PagarMeAdapter, etc.
    """

    @abstractmethod
    def create_pix_charge(
        self,
        value: Decimal,
        description: str,
        customer_id: str,
        due_date: Optional[datetime] = None,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a PIX charge (receivable).

        Args:
            value: Amount in BRL (Decimal for precision)
            description: Charge description
            customer_id: External customer identifier
            due_date: Optional expiration date
            idempotency_key: Idempotency key for duplicate prevention

        Returns:
            {
                "charge_id": str,
                "qr_code": str,  # PIX Copy-Paste code
                "qr_code_url": str,  # QR Code image URL
                "status": str,
                "expires_at": datetime
            }
        """
        pass

    @abstractmethod
    def create_pix_payment(
        self,
        value: Decimal,
        pix_key: str,
        pix_key_type: str,
        description: str,
        idempotency_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a PIX payment (payable).

        Args:
            value: Amount in BRL
            pix_key: Destination PIX key
            pix_key_type: Key type (CPF, EMAIL, PHONE, RANDOM, CNPJ)
            description: Payment description
            idempotency_key: Idempotency key

        Returns:
            {
                "payment_id": str,
                "status": str,
                "end_to_end_id": str,  # E2E transaction ID
                "processed_at": datetime
            }
        """
        pass

    @abstractmethod
    def get_charge_status(self, charge_id: str) -> Dict[str, Any]:
        """
        Retrieves current status of a PIX charge.

        Args:
            charge_id: Charge identifier

        Returns:
            {
                "charge_id": str,
                "status": str,  # PENDING, CONFIRMED, EXPIRED, CANCELLED
                "paid_at": Optional[datetime],
                "payer_info": Optional[dict]
            }
        """
        pass

    @abstractmethod
    def get_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """
        Retrieves current status of a PIX payment.

        Args:
            payment_id: Payment identifier

        Returns:
            {
                "payment_id": str,
                "status": str,  # PENDING, CONFIRMED, FAILED
                "end_to_end_id": Optional[str],
                "failure_reason": Optional[str]
            }
        """
        pass

    @abstractmethod
    def cancel_charge(self, charge_id: str) -> bool:
        """
        Cancels a pending PIX charge.

        Args:
            charge_id: Charge identifier

        Returns:
            Success flag
        """
        pass
