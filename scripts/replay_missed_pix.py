"""
Replay missed inbound PIX payments.

Fetches recent RECEIVED payments from the Asaas API that are NOT yet in the
transacoes_pix table and runs them through the same CPF/CNPJ resolver used
by the webhook handler. Credits the correct user when a match is found.

Usage:
  python scripts/replay_missed_pix.py --dry-run       # list what would be credited
  python scripts/replay_missed_pix.py                 # execute and credit users
  python scripts/replay_missed_pix.py --payment-id cus_xxx  # recover a specific payment
  python scripts/replay_missed_pix.py --days 3        # look back 3 days (default: 1)
"""
import sys
import os
import re
import argparse
from datetime import datetime, timezone, timedelta
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from sqlalchemy.orm import configure_mappers
from app.core.config import settings
from app.core.database import SessionLocal
from app.auth.models import User
from app.cards.models import CreditCard  # noqa: F401 — registers CreditCard for mapper resolution
import app.minha_conta.models  # noqa: F401 — registers UserSubscription
from app.pix.models import PixTransaction, PixStatus, TransactionType

# Force SQLAlchemy to resolve all string-based relationship references now,
# before any session.query() call — prevents KeyError on CreditCard / User lookups.
configure_mappers()


def _raw_doc(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _resolve_user(session, dest_key: str, payer_doc: str):
    """Mirror of the webhook 3-tier resolver."""
    dest_key = (dest_key or "").strip().lower()

    # Tier 1: virtual key (pix_random_key / pix_email_key)
    if dest_key:
        user = session.query(User).filter(
            (User.pix_random_key == dest_key) | (User.pix_email_key == dest_key)
        ).first()
        if user:
            return user, "virtual_key"

    # Tier 2: dest_key is a CPF/CNPJ (digits only)
    if dest_key:
        digits = _raw_doc(dest_key)
        if len(digits) in (11, 14):
            for u in session.query(User).all():
                if _raw_doc(u.cpf_cnpj or "") == digits:
                    return u, "dest_key_document"

    # Tier 3: payer CPF/CNPJ matches a platform account holder (self-deposit)
    if payer_doc and len(payer_doc) in (11, 14):
        for u in session.query(User).all():
            if _raw_doc(u.cpf_cnpj or "") == payer_doc:
                return u, "payer_document"

    return None, None


def fetch_received_payments(base_url: str, api_key: str, days: int, specific_id: str = None):
    """Fetch RECEIVED payments from Asaas REST API."""
    headers = {"access_token": api_key}

    if specific_id:
        resp = httpx.get(f"{base_url}/payments/{specific_id}", headers=headers, timeout=15.0)
        if resp.status_code != 200:
            print(f"[ERROR] Asaas returned {resp.status_code} for payment {specific_id}")
            print(resp.text[:300])
            return []
        return [resp.json()]

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    url = f"{base_url}/payments"
    params = {
        "status": "RECEIVED,CONFIRMED",
        "billingType": "PIX",
        "dateCreated[ge]": cutoff,
        "limit": 100,
        "offset": 0,
    }
    results = []
    while True:
        resp = httpx.get(url, headers=headers, params=params, timeout=15.0)
        if resp.status_code != 200:
            print(f"[ERROR] Asaas list returned {resp.status_code}")
            break
        data = resp.json()
        items = data.get("data") or []
        results.extend(items)
        if not data.get("hasMore"):
            break
        params["offset"] += len(items)
    return results


def run(dry_run: bool, days: int, specific_id: str = None):
    if not settings.ASAAS_API_KEY:
        print("[ERROR] ASAAS_API_KEY not configured. Set it in .env or environment.")
        sys.exit(1)

    base_url = (
        "https://sandbox.asaas.com/api/v3"
        if settings.ASAAS_USE_SANDBOX
        else "https://api.asaas.com/v3"
    )
    print(f"[INFO] Using {'SANDBOX' if settings.ASAAS_USE_SANDBOX else 'PRODUCTION'} API")
    print(f"[INFO] Fetching payments (lookback={days}d, specific_id={specific_id or 'none'})")

    session = SessionLocal()

    payments = fetch_received_payments(base_url, settings.ASAAS_API_KEY, days, specific_id)
    print(f"[INFO] Fetched {len(payments)} payment(s) from Asaas")

    credited = 0
    skipped_already_processed = 0
    skipped_no_match = 0

    for payment in payments:
        payment_id = payment.get("id")
        if not payment_id:
            continue

        # Check if already in DB
        existing = session.query(PixTransaction).filter(
            (PixTransaction.id == payment_id) |
            (PixTransaction.idempotency_key == f"inbound-{payment_id}")
        ).first()
        if existing:
            print(f"  [SKIP] {payment_id} — already processed (status={existing.status})")
            skipped_already_processed += 1
            continue

        # Extract pixTransaction data
        pix_raw = payment.get("pixTransaction")
        pix_data = pix_raw if isinstance(pix_raw, dict) else {}

        dest_key = (pix_data.get("pixKey") or "").strip().lower()
        payer_doc = _raw_doc(
            pix_data.get("payerDocument")
            or pix_data.get("payerCpfCnpj")
            or (payment.get("payer") or {}).get("cpfCnpj")
            or payment.get("payerCpfCnpj")
            or ""
        )
        payer_name = (
            pix_data.get("payerName")
            or payment.get("customerName")
            or "Pagador externo"
        )

        # If pixTransaction was a string, fetch the full object from API
        if not payer_doc or not dest_key:
            try:
                detail_resp = httpx.get(
                    f"{base_url}/payments/{payment_id}",
                    headers={"access_token": settings.ASAAS_API_KEY},
                    timeout=10.0,
                )
                if detail_resp.status_code == 200:
                    full = detail_resp.json()
                    pix_full = full.get("pixTransaction")
                    if isinstance(pix_full, dict):
                        dest_key = dest_key or (pix_full.get("pixKey") or "").strip().lower()
                        payer_doc = payer_doc or _raw_doc(
                            pix_full.get("payerDocument")
                            or pix_full.get("payerCpfCnpj")
                            or ""
                        )
                        payer_name = pix_full.get("payerName") or payer_name
            except Exception as e:
                print(f"  [WARN] API detail call failed for {payment_id}: {e}")

        raw_value = payment.get("value") or pix_data.get("value") or 0
        try:
            inbound_value = float(raw_value)
        except (TypeError, ValueError):
            inbound_value = 0.0

        if inbound_value <= 0:
            print(f"  [SKIP] {payment_id} — value={inbound_value} (zero or missing)")
            continue

        user, tier = _resolve_user(session, dest_key, payer_doc)

        if not user:
            print(
                f"  [NO MATCH] {payment_id} value=R${inbound_value:.2f} "
                f"dest_key={dest_key!r} payer_doc_len={len(payer_doc)}"
            )
            skipped_no_match += 1
            continue

        print(
            f"  [MATCH] {payment_id} -> user={user.id} ({user.name}) "
            f"tier={tier} value=R${inbound_value:.2f} "
            f"current_balance=R${user.balance:.2f}"
        )

        if dry_run:
            print(f"  [DRY RUN] Would credit R${inbound_value:.2f} to {user.name}")
            credited += 1
            continue

        # Apply credit
        prev_balance = user.balance
        user.balance = round(user.balance + inbound_value, 2)
        user.credit_limit = round(getattr(user, "credit_limit", 0) + inbound_value * 0.50, 2)
        session.add(user)

        eff_key = dest_key or payer_doc or "unknown"
        eff_digits = _raw_doc(eff_key)
        eff_key_type = (
            "ALEATORIA" if (len(eff_key) == 36 and "-" in eff_key)
            else "CPF" if len(eff_digits) == 11
            else "CNPJ" if len(eff_digits) == 14
            else "EMAIL"
        )
        new_tx = PixTransaction(
            id=payment_id,
            value=inbound_value,
            pix_key=eff_key,
            key_type=eff_key_type,
            type=TransactionType.RECEIVED,
            status=PixStatus.CONFIRMED,
            user_id=user.id,
            idempotency_key=f"inbound-{payment_id}",
            description=f"PIX recebido de {payer_name} [replay]",
            recipient_name=payer_name,
            fee_amount=0.0,
        )
        session.add(new_tx)
        session.commit()
        session.refresh(user)

        print(
            f"  [CREDITED] R${inbound_value:.2f} -> {user.name} | "
            f"balance: R${prev_balance:.2f} -> R${user.balance:.2f}"
        )
        credited += 1

    session.close()
    print()
    print(f"--- Summary ---")
    print(f"  Credited:                 {credited}")
    print(f"  Already processed (skip): {skipped_already_processed}")
    print(f"  No matching user:         {skipped_no_match}")
    if dry_run:
        print("  [DRY RUN — no changes written to DB]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay missed inbound PIX payments")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be credited without writing")
    parser.add_argument("--days", type=int, default=1, help="Lookback window in days (default: 1)")
    parser.add_argument("--payment-id", type=str, default=None, help="Replay a specific Asaas payment ID")
    args = parser.parse_args()
    run(dry_run=args.dry_run, days=args.days, specific_id=args.payment_id)
