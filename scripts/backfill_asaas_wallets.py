"""
Backfill script: Create Asaas subcontas for existing users without asaas_wallet_id.

Queries all active users where asaas_wallet_id IS NULL (excluding matrix/admin
internal accounts), calls Asaas POST /v3/accounts for each, and persists the
returned walletId.

SAFETY:
- Idempotent: skips users that already have asaas_wallet_id
- Non-destructive: read-only on failure, writes only on success
- Rate-limited: 1 second delay between API calls to respect Asaas limits
- Dry-run mode: pass --dry-run to preview without API calls

Run with:
    python scripts/backfill_asaas_wallets.py
    python scripts/backfill_asaas_wallets.py --dry-run
"""
import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.core.database import engine
from app.core.config import settings
from app.core.logger import logger
from app.auth.models import User
from app.adapters.gateway_factory import get_payment_gateway


def run_backfill(dry_run: bool = False) -> None:
    gateway = get_payment_gateway()

    if gateway is None:
        print("ERROR: ASAAS_API_KEY not configured. Cannot create subcontas.")
        sys.exit(1)

    if not hasattr(gateway, "create_subconta"):
        print("ERROR: AsaasAdapter does not have create_subconta method.")
        sys.exit(1)

    with Session(engine) as db:
        candidates = (
            db.query(User)
            .filter(
                User.asaas_wallet_id.is_(None),
                User.is_active.is_(True),
                User.email != settings.MATRIX_ACCOUNT_EMAIL,
            )
            .order_by(User.created_at)
            .all()
        )

    total = len(candidates)
    print(f"Users without asaas_wallet_id: {total}")
    if dry_run:
        print("Dry-run mode: no API calls will be made.")
        for u in candidates:
            print(f"  would process: id={u.id} email={u.email} phone={bool(u.phone)} zip={bool(u.address_zip)}")
        return

    success = 0
    skipped = 0
    failed = 0

    with Session(engine) as db:
        for idx, u in enumerate(candidates, start=1):
            user = db.merge(u)
            print(f"[{idx}/{total}] Processing user {user.id} ({user.email})...", end=" ")

            # Skip if missing required fields for Asaas subconta creation
            if not user.phone or not user.address_zip or not user.address_street:
                print("SKIP (missing phone/address fields)")
                skipped += 1
                continue

            try:
                wallet_id = gateway.create_subconta(
                    name=user.name,
                    email=user.email,
                    cpf_cnpj=user.cpf_cnpj,
                    mobile_phone=user.phone,
                    address=user.address_street,
                    address_number=user.address_number or "S/N",
                    postal_code=user.address_zip,
                    city=user.address_city or "",
                    state=user.address_state or "",
                )
                user.asaas_wallet_id = wallet_id
                db.commit()
                print(f"OK walletId={wallet_id}")
                success += 1
            except Exception as e:
                db.rollback()
                print(f"FAIL: {e}")
                logger.warning(f"backfill_asaas_wallets: failed for user={user.id}: {e}")
                failed += 1

            # Respect Asaas rate limits (avoid 429)
            time.sleep(1.0)

    print(f"\nBackfill complete: success={success} skipped={skipped} failed={failed}")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill Asaas walletId for existing users")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making API calls")
    args = parser.parse_args()
    run_backfill(dry_run=args.dry_run)
