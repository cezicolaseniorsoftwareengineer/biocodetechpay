"""
Additional PIX schemas for Asaas integration.
Extends existing schemas with real gateway functionality.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class PixChargeCreateRequest(BaseModel):
    """Request to create a PIX charge (receivable) with QR Code."""
    value: float = Field(..., gt=0, le=1000000, description="Charge value in BRL")
    description: str = Field(..., min_length=1, max_length=500, description="Charge description")


class PixChargeCreateResponse(BaseModel):
    """Response after creating a PIX charge."""
    charge_id: str = Field(..., description="Charge unique identifier")
    qr_code: str = Field(..., description="PIX copy-paste code (Copia e Cola)")
    qr_code_url: Optional[str] = Field(None, description="QR Code image URL (Base64)")
    value: float = Field(..., description="Charge value")
    status: str = Field(..., description="Charge status (CREATED, CONFIRMED, EXPIRED)")
    expires_at: Optional[datetime] = Field(None, description="Expiration date/time")
    created_at: datetime = Field(..., description="Creation timestamp")


class PixPaymentExecuteRequest(BaseModel):
    """Request to execute a PIX payment (transfer)."""
    pix_transaction_id: str = Field(..., description="Local PIX transaction ID to execute")


class PixPaymentExecuteResponse(BaseModel):
    """Response after submitting a PIX payment."""
    payment_id: str = Field(..., description="Payment unique identifier")
    status: str = Field(..., description="Payment status (PROCESSING, CONFIRMED, FAILED)")
    end_to_end_id: Optional[str] = Field(None, description="End-to-end transaction ID")
    submitted_at: datetime = Field(..., description="Submission timestamp")
