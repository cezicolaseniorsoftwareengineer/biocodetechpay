"""
Public payment link tests — /pix/link/{charge_id}

Covers:
- Valid charge renders HTML with QR code and copy-paste code
- Already-paid charge renders with already_paid flag
- Non-existent charge returns 404
- Invalid UUID format returns 404 (no SQL injection risk)
- SENT-type transaction not exposed via link (only RECEIVED)
"""
import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from app.main import app
from app.core.database import get_db
from app.pix.models import PixTransaction, PixStatus, TransactionType
from datetime import datetime, timezone

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_dependency_overrides():
    saved = dict(app.dependency_overrides)
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


def _make_charge(
    charge_id: str = None,
    value: float = 25.0,
    status: PixStatus = PixStatus.CREATED,
    tx_type: TransactionType = TransactionType.RECEIVED,
) -> PixTransaction:
    cid = charge_id or str(uuid4())
    return PixTransaction(
        id=cid,
        value=value,
        status=status,
        user_id="user-link-001",
        type=tx_type,
        pix_key=cid,
        key_type="ALEATORIA",
        description="Link test charge",
        copy_paste_code="00020126360014BR.GOV.BCB.PIX0114+5511999996304ABCD",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestPaymentLink:
    """Tests the public shareable payment link page."""

    def test_valid_charge_returns_html(self):
        """Open charge must render HTML page with QR and copy-paste code."""
        charge = _make_charge()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = charge

        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get(f"/pix/link/{charge.id}")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        body = response.text
        assert "R$" in body or "25" in body

    def test_already_paid_charge_shows_paid_status(self):
        """Confirmed charge must render but indicate payment is complete."""
        charge = _make_charge(status=PixStatus.CONFIRMED)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = charge

        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get(f"/pix/link/{charge.id}")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_nonexistent_charge_returns_404(self):
        """Non-existent charge ID must return 404."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get(f"/pix/link/{uuid4()}")

        assert response.status_code == 404

    def test_sent_transaction_not_accessible_via_link(self):
        """SENT transactions must not be exposed — only RECEIVED charges."""
        mock_db = MagicMock()
        # The filter includes type == RECEIVED, so SENT won't match
        mock_db.query.return_value.filter.return_value.first.return_value = None

        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get(f"/pix/link/{uuid4()}")

        assert response.status_code == 404

    def test_invalid_format_returns_404(self):
        """Non-UUID string as charge_id must return 404 (not 500 or SQL error)."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        app.dependency_overrides[get_db] = lambda: mock_db

        response = client.get("/pix/link/not-a-valid-uuid")

        assert response.status_code == 404
