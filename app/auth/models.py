from sqlalchemy import String, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional, TYPE_CHECKING
from app.core.database import Base

if TYPE_CHECKING:
    from app.cards.models import CreditCard


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column("nome", String(100), nullable=False)
    cpf_cnpj: Mapped[str] = mapped_column("cpf_cnpj", String(20), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column("email", String(100), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column("hashed_password", String(255), nullable=False)
    balance: Mapped[float] = mapped_column("saldo", Float, default=0.00, nullable=False)
    credit_limit: Mapped[float] = mapped_column("limite_credito", Float, default=10000.00, nullable=False)
    created_at: Mapped[datetime] = mapped_column("criado_em", DateTime, default=lambda: datetime.now(timezone.utc))
    asaas_customer_id: Mapped[Optional[str]] = mapped_column("asaas_customer_id", String(100), nullable=True, index=True)
    cards = relationship("CreditCard", back_populates="user", lazy="select")
