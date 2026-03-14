"""
Simulacao de pagamento QR Code real — RAZECSHOPPING (email key).

Payload fornecido pelo usuario (maquininha real):
  00020126510014br.gov.bcb.pix0129razecshoppingonline@gmail.com
  52040000530398654041.005802BR5913RAZECSHOPPING6008So Paulo
  62250521mpqrinter149661742843630484B7

Fluxo:
  1. Validacao CRC local (deve ser 84B7)
  2. POST /pix/qrcode/consultar  -> Stage 2 field-54: value=1.00, merchant=RAZECSHOPPING
  3. POST /pix/qrcode/pagar      -> Asaas producao POST /pix/qrCodes/pay
  4. Comprovante: status, payment_id, Neon DB
  5. Verificacao pós-pagamento no banco

Executar:
    python scripts/simulate_razecshopping.py --password SENHA --yes
    SIM_PASSWORD=SENHA SIM_YES=1 python scripts/simulate_razecshopping.py
"""
import sys
import os
import argparse

os.environ["BIO_CODE_TECH_PAY_ALLOWED_START"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importar TODOS os modelos antes de qualquer query ORM (resolve CreditCard relationship)
import app.cards.models   # noqa
import app.boleto.models  # noqa
import app.pix.models     # noqa
import app.parcelamento.models  # noqa

from sqlalchemy import text
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal

PAYLOAD = (
    "00020126510014br.gov.bcb.pix0129razecshoppingonline@gmail.com"
    "52040000530398654041.005802BR5913RAZECSHOPPING6008So Paulo"
    "62250521mpqrinter149661742843630484B7"
)

def _crc16_ccitt(data: str) -> str:
    crc = 0xFFFF
    for byte in data.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return format(crc, "04X")


def verify_crc(payload: str) -> tuple:
    idx = payload.rfind("6304")
    if idx == -1:
        return False, "campo 63 nao encontrado"
    body = payload[:idx + 4]
    expected = _crc16_ccitt(body)
    actual = payload[idx + 4:idx + 8].upper()
    return (expected == actual), f"expected={expected} actual={actual}"


def find_admin(db):
    """Busca usuario admin pelo email canonico."""
    row = db.execute(text(
        "SELECT cpf_cnpj, email, saldo FROM users "
        "WHERE email = 'biocodetechnology@gmail.com' LIMIT 1"
    )).fetchone()
    if not row:
        # Tentar por CNPJ conhecido
        row = db.execute(text(
            "SELECT cpf_cnpj, email, saldo FROM users "
            "WHERE cpf_cnpj = '61425124000103' LIMIT 1"
        )).fetchone()
    return row


def run():
    parser = argparse.ArgumentParser(description="Simula pagamento QR Code RAZECSHOPPING")
    parser.add_argument("--password", default=os.environ.get("SIM_PASSWORD", ""),
                        help="Senha do usuario admin (ou env SIM_PASSWORD)")
    parser.add_argument("--yes", action="store_true",
                        default=bool(os.environ.get("SIM_YES", "")),
                        help="Confirmar automaticamente o pagamento real")
    args = parser.parse_args()

    print("=" * 70)
    print("  BioCodeTechPay — Simulacao de Pagamento QR Code Real")
    print("  Beneficiario: RAZECSHOPPING | Chave: razecshoppingonline@gmail.com")
    print("  Valor: R$ 1,00")
    print("=" * 70)

    # --- 0. Validacao CRC ---
    crc_ok, crc_detail = verify_crc(PAYLOAD)
    print(f"\n[CRC] {'OK' if crc_ok else 'FALHOU'} — {crc_detail}")
    if not crc_ok:
        print("  ERRO: payload corrompido — abortando")
        sys.exit(1)

    # --- 1. Buscar admin no Neon ---
    db = SessionLocal()
    admin_row = find_admin(db)
    db.close()

    if not admin_row:
        print("\n[ADMIN] Usuario nao encontrado no Neon. Verifique o banco.")
        print("  Tente: python scripts/set_password.py --cpf <CPF> --password <SENHA>")
        sys.exit(1)

    cpf_admin = admin_row[0]
    email_admin = admin_row[1]
    balance_admin = admin_row[2]

    print(f"\n[ADMIN]")
    print(f"  cpf_cnpj : {cpf_admin}")
    print(f"  email    : {email_admin}")
    print(f"  saldo    : R$ {float(balance_admin):.2f}")

    if float(balance_admin) < 1.00:
        print(f"\n  AVISO: saldo insuficiente (R$ {float(balance_admin):.2f}) para pagar R$ 1,00")
        if not args.yes:
            print("  O Asaas pode rejeitar por saldo. Continue? [s/N]: ", end="")
            resp = input().strip().lower()
            if resp != "s":
                sys.exit(0)

    # Senha: --password arg > SIM_PASSWORD env > prompt interativo
    senha = args.password
    if not senha:
        print("\nDigite a senha do admin (ou Enter para usar 'admin.BioCodeTechPay'): ", end="")
        senha = input().strip() or "admin.BioCodeTechPay"

    client = TestClient(app, raise_server_exceptions=False)

    # --- 2. Login ---
    print(f"\n[AUTH] POST /auth/login como {cpf_admin}...")
    login_resp = client.post("/auth/login", json={
        "cpf_cnpj": cpf_admin,
        "password": senha
    })
    print(f"  Status: {login_resp.status_code}")
    if login_resp.status_code != 200:
        print(f"  ERRO: {login_resp.text[:300]}")
        sys.exit(1)

    token = login_resp.json().get("access_token")
    if not token:
        token = client.cookies.get("access_token", "").replace("Bearer ", "")
    cookies = {"access_token": f"Bearer {token}"}
    print(f"  Token obtido: {'sim' if token else 'NAO'}")

    # --- 3. Consultar ---
    print(f"\n[CONSULTAR] POST /pix/qrcode/consultar...")
    consultar_resp = client.post(
        "/pix/qrcode/consultar",
        json={"payload": PAYLOAD},
        cookies=cookies
    )
    print(f"  Status: {consultar_resp.status_code}")
    print(f"  Body  : {consultar_resp.text[:500]}")

    if consultar_resp.status_code != 200:
        print("\n  ERRO na consulta — abortando")
        sys.exit(1)

    consultar_data = consultar_resp.json()
    print(f"\n  valor         : R$ {consultar_data.get('value'):.2f}")
    print(f"  beneficiario  : {consultar_data.get('beneficiary_name')}")
    print(f"  is_internal   : {consultar_data.get('is_internal')}")

    # --- 4. Confirmar com usuario ---
    if not args.yes:
        print(f"\nExecutar pagamento REAL de R$ 1,00 para RAZECSHOPPING via Asaas producao? [s/N]: ", end="")
        confirm = input().strip().lower()
        if confirm != "s":
            print("Pagamento cancelado pelo usuario.")
            sys.exit(0)
    else:
        print("\n[AUTO-CONFIRM] --yes ativo: pagamento sera executado automaticamente")

    # --- 5. Pagar ---
    import uuid
    idempotency_key = str(uuid.uuid4())
    print(f"\n[PAGAR] POST /pix/qrcode/pagar (idempotency={idempotency_key[:8]}...)...")
    pagar_resp = client.post(
        "/pix/qrcode/pagar",
        json={
            "payload": PAYLOAD,
            "description": "BioCodeTechPay QR RAZECSHOPPING simulacao"
        },
        headers={"X-Idempotency-Key": idempotency_key},
        cookies=cookies
    )
    print(f"  Status: {pagar_resp.status_code}")
    print(f"  Body  : {pagar_resp.text[:800]}")

    if pagar_resp.status_code not in (200, 201):
        print("\n  PAGAMENTO FALHOU — ver detalhe acima")
        sys.exit(1)

    pagar_data = pagar_resp.json()
    payment_id = pagar_data.get("id") or pagar_data.get("payment_id")
    status_pagamento = pagar_data.get("status")
    valor_pago = pagar_data.get("value")

    # --- 6. Comprovante ---
    print("\n" + "=" * 70)
    print("  COMPROVANTE DE PAGAMENTO")
    print("=" * 70)
    print(f"  payment_id    : {payment_id}")
    print(f"  status        : {status_pagamento}")
    print(f"  valor         : R$ {float(valor_pago or 1.00):.2f}")
    print(f"  beneficiario  : {pagar_data.get('receiver_name') or 'RAZECSHOPPING'}")
    print(f"  chave pix     : razecshoppingonline@gmail.com")
    print(f"  descricao     : {pagar_data.get('description', 'PIX QR Code Payment')}")
    print(f"  correlation   : {pagar_data.get('correlation_id', 'N/A')}")
    print("=" * 70)

    # --- 7. Verificar no Neon ---
    print("\n[NEON DB] Verificando transacao persistida...")
    db2 = SessionLocal()
    if payment_id:
        tx_row = db2.execute(text(
            "SELECT id, value, status, type, recipient_name, created_at "
            "FROM transacoes_pix WHERE id = :pid LIMIT 1"
        ), {"pid": payment_id}).fetchone()
        if tx_row:
            print(f"  id             : {tx_row[0]}")
            print(f"  value          : R$ {float(tx_row[1]):.2f}")
            print(f"  status         : {tx_row[2]}")
            print(f"  type           : {tx_row[3]}")
            print(f"  recipient_name : {tx_row[4]}")
            print(f"  created_at     : {tx_row[5]}")
        else:
            print(f"  Transacao {payment_id} nao encontrada no Neon ainda (pode ser assíncrona)")

    admin_after = db2.execute(text(
        "SELECT saldo FROM users WHERE cpf_cnpj = :cpf"
    ), {"cpf": cpf_admin}).fetchone()
    if admin_after:
        saldo_depois = float(admin_after[0])
        saldo_antes = float(balance_admin)
        print(f"\n  Saldo antes    : R$ {saldo_antes:.2f}")
        print(f"  Saldo depois   : R$ {saldo_depois:.2f}")
        print(f"  Diferenca      : R$ {saldo_antes - saldo_depois:.2f}")
    db2.close()

    print("\n[OK] Simulacao concluida.")


if __name__ == "__main__":
    run()
