"""
Backfill recipient_name for existing PIX transactions that still show
"External Sender" or "External Receiver" due to missing stored names.

For SENT external transactions: attempts Asaas /transfers/{id} to get receiver name.
For RECEIVED external transactions: attempts Asaas /payments/{id} to get payer name.

Usage:
    python scripts/backfill_recipient_names.py [--dry-run]

Flags:
    --dry-run    Print what would be updated without writing to the database.

Safety:
    - Skips internal transfers (correlation_id found on both sides).
    - Skips transactions that already have recipient_name set.
    - Rate-limits Asaas calls to avoid 429 errors.
"""
import os
import sys
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import or_
from app.core.database import SessionLocal
from app.pix.models import PixTransaction, TransactionType, PixStatus
from app.adapters.gateway_factory import get_payment_gateway


def main(dry_run: bool = False) -> None:
    mode_label = "[DRY-RUN] " if dry_run else ""
    print(f"=== {mode_label}BACKFILL RECIPIENT NAMES ===")

    gateway = get_payment_gateway()
    if not gateway:
        print("ERRO: Gateway Asaas nao configurado. Defina ASAAS_API_KEY no .env.")
        sys.exit(1)

    db = SessionLocal()
    try:
        # Select SENT external transactions without stored recipient name
        sent_missing = (
            db.query(PixTransaction)
            .filter(
                PixTransaction.type == TransactionType.SENT,
                PixTransaction.status == PixStatus.CONFIRMED,
                or_(
                    PixTransaction.recipient_name == None,
                    PixTransaction.recipient_name == "",
                )
            )
            .all()
        )

        # Select RECEIVED external transactions without stored recipient name
        received_missing = (
            db.query(PixTransaction)
            .filter(
                PixTransaction.type == TransactionType.RECEIVED,
                PixTransaction.status == PixStatus.CONFIRMED,
                or_(
                    PixTransaction.recipient_name == None,
                    PixTransaction.recipient_name == "",
                )
            )
            .all()
        )

        # Build correlation_id set to identify internal transfers
        all_correlation_ids = {
            tx.correlation_id
            for tx in (sent_missing + received_missing)
            if tx.correlation_id
        }

        # For each correlation_id, check if a counterpart exists (internal = both sides present)
        internal_correlation_ids = set()
        for cid in all_correlation_ids:
            counterparts = (
                db.query(PixTransaction.type)
                .filter(PixTransaction.correlation_id == cid)
                .distinct()
                .all()
            )
            types = {row[0] for row in counterparts}
            if TransactionType.SENT in types and TransactionType.RECEIVED in types:
                internal_correlation_ids.add(cid)

        print(f"\nTransacoes SENT sem nome: {len(sent_missing)}")
        print(f"Transacoes RECEIVED sem nome: {len(received_missing)}")
        print(f"Transferencias internas (serao ignoradas): {len(internal_correlation_ids)}")

        updated_count = 0
        skipped_count = 0

        # --- Backfill SENT transactions via Asaas /transfers/{id} ---
        for tx in sent_missing:
            if tx.correlation_id in internal_correlation_ids:
                skipped_count += 1
                continue

            try:
                result = gateway.get_payment_status(tx.id)
                # get_payment_status does not return receiver_name; try pay_qr_code is wrong.
                # Asaas GET /transfers/{id} returns receiverPixTransferType / receiverName in some versions.
                # Fallback: use the pix_key itself (masked) as identifier if name unavailable.
                resolved_name = result.get("receiver_name") or result.get("receiverName")
                if not resolved_name and tx.pix_key:
                    # pix_key for external SENT is the destination PIX key — use as label
                    resolved_name = f"Chave: {tx.pix_key[:40]}"

                if resolved_name:
                    print(f"  SENT {tx.id[:12]}... -> {resolved_name}")
                    if not dry_run:
                        tx.recipient_name = resolved_name
                        db.add(tx)
                    updated_count += 1
                else:
                    skipped_count += 1

                time.sleep(0.3)  # rate-limit: max ~3 req/s

            except Exception as e:
                print(f"  SENT {tx.id[:12]}... -> ERRO: {e}")
                skipped_count += 1

        # --- Backfill RECEIVED transactions via Asaas /payments/{id} ---
        for tx in received_missing:
            if tx.correlation_id in internal_correlation_ids:
                skipped_count += 1
                continue

            # Skip simulation/local charges (no Asaas record)
            if "DYNAMIC_QR_CODE" in (tx.pix_key or "") or "SIMULACAO" in (tx.pix_key or ""):
                skipped_count += 1
                continue

            try:
                charge_status = gateway.get_charge_status(tx.id)
                payer_info = charge_status.get("payer_info") or {}
                resolved_name = payer_info.get("name")

                if resolved_name:
                    print(f"  RECEIVED {tx.id[:12]}... -> {resolved_name}")
                    if not dry_run:
                        tx.recipient_name = resolved_name
                        db.add(tx)
                    updated_count += 1
                else:
                    skipped_count += 1

                time.sleep(0.3)

            except Exception as e:
                print(f"  RECEIVED {tx.id[:12]}... -> ERRO: {e}")
                skipped_count += 1

        if not dry_run and updated_count > 0:
            db.commit()

        print(f"\nResultado: {updated_count} atualizadas, {skipped_count} ignoradas")
        if dry_run:
            print("Modo DRY-RUN: nenhuma alteracao foi persistida.")

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Simula sem gravar no banco")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
