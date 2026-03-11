"""
Transaction fee calculation engine — Bio Code Tech Pay.

Fee policy:
  Gateway cost (Asaas):
    - Every external PIX sent:   R$ 2.00 (Asaas charges this from our account)
    - This cost is always passed through to the client + our margin on top.

  PF (CPF — 11 raw digits)
    - External PIX sent:     R$ 2.50 fixed (R$ 2.00 Asaas cost + R$ 0.50 margin)
    - External PIX received: free
    - Boleto payment:        R$ 1.00 fixed
    - Internal transfer:     free

  PJ (CNPJ — 14 raw digits)
    - External PIX sent:     max(R$ 3.00, 0.8% of value)  — R$ 3.00 covers Asaas R$ 2.00 + R$ 1.00 margin
    - External PIX received: 0.495% of value
    - Boleto payment:        R$ 1.75 fixed
    - Internal transfer:     free

All internal transfers (Bio Code Tech Pay -> Bio Code Tech Pay) are always free.

ASAAS_PIX_OUTBOUND_COST: what Asaas charges us per outbound PIX transfer.
Update this constant when Asaas changes their pricing.
"""
from decimal import Decimal, ROUND_HALF_UP
import re


_TWO_PLACES = Decimal("0.01")

# ----------------------------------------------------------------- Gateway cost
# Asaas charges this from our account on EVERY external PIX sent.
# Evidence: R$ 0.25 transfer -> Asaas debited R$ 2.00 as fee (11/03/2026).
# Our client fee must always cover this cost plus our margin.
ASAAS_PIX_OUTBOUND_COST = Decimal("2.00")

# --------------------------------------------------------------------------- PF
_PIX_SENT_PF = Decimal("2.50")   # covers ASAAS_PIX_OUTBOUND_COST (R$2.00) + R$0.50 margin
_PIX_RECV_PF = Decimal("0.00")
_BOLETO_PF   = Decimal("1.00")

# --------------------------------------------------------------------------- PJ
_PIX_SENT_RATE_PJ  = Decimal("0.0080")   # 0.8% of value
_PIX_SENT_MIN_PJ   = Decimal("3.00")    # minimum: R$2.00 Asaas + R$1.00 margin
_PIX_RECV_RATE_PJ  = Decimal("0.00495")
_BOLETO_PJ         = Decimal("1.75")


def _raw_digits(cpf_cnpj) -> str:
    if not isinstance(cpf_cnpj, str):
        cpf_cnpj = str(cpf_cnpj) if cpf_cnpj is not None else ""
    return re.sub(r"\D", "", cpf_cnpj)


def is_pj(cpf_cnpj: str) -> bool:
    """Returns True when the document is a CNPJ (14 digits)."""
    return len(_raw_digits(cpf_cnpj)) == 14


def calculate_pix_fee(
    cpf_cnpj: str,
    amount: float,
    *,
    is_external: bool,
    is_received: bool = False,
) -> Decimal:
    """
    Calculates PIX transaction fee.

    Args:
        cpf_cnpj: Raw CPF or CNPJ string of the account holder.
        amount:   Transaction value in BRL.
        is_external: True for external (inter-bank) transfers; False for internal.
        is_received: True when the transaction is incoming (charge paid by third party).

    Returns:
        Fee amount as Decimal rounded to 2 decimal places.
    """
    if not is_external:
        return Decimal("0.00")

    value = Decimal(str(amount))

    if is_pj(cpf_cnpj):
        if is_received:
            return (value * _PIX_RECV_RATE_PJ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
        fee = value * _PIX_SENT_RATE_PJ
        return max(fee, _PIX_SENT_MIN_PJ).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    else:
        return _PIX_RECV_PF if is_received else _PIX_SENT_PF


def calculate_boleto_fee(cpf_cnpj: str) -> Decimal:
    """Returns the fixed fee for boleto payments based on account type."""
    return _BOLETO_PJ if is_pj(cpf_cnpj) else _BOLETO_PF


def fee_display(fee: Decimal) -> str:
    """
    Formats a fee amount as a human-readable Brazilian Real string.
    Returns 'Gratuito' when zero.
    """
    if fee == Decimal("0.00"):
        return "Gratuito"
    formatted = f"{float(fee):.2f}".replace(".", ",")
    return f"R$ {formatted}"
