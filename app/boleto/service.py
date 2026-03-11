from uuid import uuid4
from sqlalchemy.orm import Session
from app.boleto.models import BoletoTransaction, BoletoStatus
from app.boleto.schemas import BoletoPaymentRequest, BoletoDetails
from app.pix.service import get_balance
from app.core.logger import logger, audit_log
from app.core.fees import calculate_boleto_fee, fee_display
from app.core.matrix import credit_fee
from app.auth.models import User
from datetime import date, timedelta
import secrets


def query_boleto(barcode: str) -> BoletoDetails:
    # Mock validation
    if not barcode.isdigit() or len(barcode) < 44:
        raise ValueError("Invalid barcode")

    if barcode.endswith("0000"):
        raise ValueError("Boleto expired or not found")

    # Mock details
    return BoletoDetails(
        barcode=barcode,
        beneficiary=f"Mock Company {secrets.randbelow(100) + 1} LTDA",
        value=float(f"{secrets.randbelow(491) + 10}.{secrets.randbelow(100)}"),
        due_date=date.today() + timedelta(days=secrets.randbelow(10) + 1)
    )


def process_payment(
    db: Session,
    data: BoletoPaymentRequest,
    user_id: str,
    correlation_id: str
) -> BoletoTransaction:

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("User not found")

    fee = calculate_boleto_fee(user.cpf_cnpj)
    total_required = data.value + float(fee)

    balance = get_balance(db, user_id)
    if balance < total_required:
        raise ValueError(
            f"Saldo insuficiente. Disponivel: R$ {balance:.2f}, "
            f"Necessario: R$ {total_required:.2f} "
            f"(valor R$ {data.value:.2f} + taxa {fee_display(fee)})"
        )

    # Debit balance including fee
    user.balance -= total_required
    db.add(user)

    # Credit fee to BioCodeTechPay matrix account (same transaction)
    credit_fee(db, float(fee))

    boleto = BoletoTransaction(
        id=str(uuid4()),
        value=data.value,
        barcode=data.barcode,
        description=data.description,
        status=BoletoStatus.PAID,
        user_id=user_id,
        correlation_id=correlation_id,
        fee_amount=float(fee),
    )

    db.add(boleto)
    db.commit()
    db.refresh(boleto)

    audit_log(
        action="boleto_paid",
        user=user_id,
        resource=f"boleto_id={boleto.id}",
        details={
            "correlation_id": correlation_id,
            "value": data.value,
            "fee_amount": float(fee),
            "total_charged": total_required,
            "barcode": data.barcode
        }
    )

    logger.info(f"Boleto paid: id={boleto.id}, value={data.value}, fee={fee_display(fee)}")
    return boleto
