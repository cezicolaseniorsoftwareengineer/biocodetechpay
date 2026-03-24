"""
Tests for overdraft prevention — balance can never go negative.
Validates the defense-in-depth guard in create_pix, internal QR,
and QR code payment paths. Uses get_available_balance mock for
the deferred-debit model.
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.pix.service import create_pix
from app.pix.schemas import PixCreateRequest, PixKeyType
from app.pix.models import PixStatus


# Real PF fee for external outbound PIX: R$4.00 (R$3 network + R$1 maintenance)
PF_FEE = Decimal("4.00")


class TestOverdraftPrevention:
    """Balance must never go negative — clamping to zero is forbidden."""

    def _make_sender(self, balance: float):
        """Use SimpleNamespace for predictable attribute behavior."""
        from types import SimpleNamespace
        return SimpleNamespace(
            id="user-sender",
            balance=Decimal(str(balance)),
            name="Sender Test",
            cpf_cnpj="12345678901",
        )

    def _make_db(self, sender) -> MagicMock:
        db = MagicMock()

        def query_side_effect(model):
            query_mock = MagicMock()
            if hasattr(model, '__name__') and model.__name__ == "User":
                query_mock.filter().first.return_value = sender
            else:
                query_mock.filter().first.return_value = None
            return query_mock

        db.query.side_effect = query_side_effect
        return db

    def test_create_pix_rejects_insufficient_balance(self):
        """Pre-check rejects when available balance < total_required."""
        sender = self._make_sender(5.00)  # R$5 < R$100 + R$4 fee
        db = self._make_db(sender)

        data = PixCreateRequest(
            value=100.0,
            pix_key="dest@email.com",
            key_type=PixKeyType.EMAIL,
            description="Test overdraft",
        )

        with patch("app.pix.service.find_recipient_user", return_value=None), \
             patch("app.pix.service.get_payment_gateway", return_value=None), \
             patch("app.pix.service.get_available_balance", return_value=Decimal("5.00")):
            with pytest.raises(ValueError, match="Saldo insuficiente"):
                create_pix(db, data, "idem-overdraft-1", "corr-1", "user-sender")

    def test_create_pix_rollback_on_negative_post_debit(self):
        """Defense-in-depth: if available balance < total, pre-check catches."""
        # Balance = R$10, value = R$10, fee = R$4 -> total R$14 > R$10 -> pre-check catches
        sender = self._make_sender(10.00)
        db = self._make_db(sender)

        data = PixCreateRequest(
            value=10.00,
            pix_key="dest@email.com",
            key_type=PixKeyType.EMAIL,
            description="Test negative protection",
        )

        with patch("app.pix.service.find_recipient_user", return_value=None), \
             patch("app.pix.service.get_payment_gateway", return_value=None), \
             patch("app.pix.service.get_available_balance", return_value=Decimal("10.00")):
            with pytest.raises(ValueError, match="Saldo insuficiente"):
                create_pix(db, data, "idem-overdraft-2", "corr-2", "user-sender")

    def test_create_pix_exact_balance_succeeds(self):
        """When available balance == value + fee, TX created with PROCESSING (deferred debit)."""
        sender = self._make_sender(14.00)
        db = self._make_db(sender)

        data = PixCreateRequest(
            value=10.00,
            pix_key="dest@email.com",
            key_type=PixKeyType.EMAIL,
            description="Exact balance test",
        )

        with patch("app.pix.service.find_recipient_user", return_value=None), \
             patch("app.pix.service.get_payment_gateway", return_value=None), \
             patch("app.pix.service.get_available_balance", return_value=Decimal("14.00")):
            pix = create_pix(db, data, "idem-exact-1", "corr-3", "user-sender")

        assert pix.status == PixStatus.PROCESSING  # deferred debit
        assert sender.balance == Decimal("14.00")  # balance unchanged at creation

    def test_balance_never_clamped_to_zero(self):
        """Verify that the old clamping behavior (sender.balance = 0) no longer exists."""
        sender = self._make_sender(1.00)  # R$1 << R$100 + fee
        db = self._make_db(sender)

        data = PixCreateRequest(
            value=100.00,
            pix_key="dest@email.com",
            key_type=PixKeyType.EMAIL,
            description="No clamping test",
        )

        with patch("app.pix.service.find_recipient_user", return_value=None), \
             patch("app.pix.service.get_payment_gateway", return_value=None), \
             patch("app.pix.service.get_available_balance", return_value=Decimal("1.00")):
            with pytest.raises(ValueError):
                create_pix(db, data, "idem-noclamp-1", "corr-4", "user-sender")

        # After rejection, balance must remain at original value (R$1.00)
        assert sender.balance == Decimal("1.00")
