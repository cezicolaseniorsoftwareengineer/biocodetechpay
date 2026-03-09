"""
Asaas Authorization Diagnostic Script.

Checks the current state of automatic transfer authorization and
prints exact steps to fix any missing configuration.

Usage:
    python scripts/check_asaas_auth.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import httpx
from app.core.config import settings

SEPARATOR = "-" * 60


def check(label: str, ok: bool, detail: str = "") -> bool:
    status = "OK    " if ok else "FAIL  "
    print(f"  [{status}] {label}")
    if detail:
        print(f"          {detail}")
    return ok


def main():
    print()
    print(SEPARATOR)
    print("  ASAAS AUTHORIZATION DIAGNOSTIC")
    print(SEPARATOR)

    all_ok = True

    # 1. ASAAS_API_KEY
    has_api_key = bool(settings.ASAAS_API_KEY)
    ok = check("ASAAS_API_KEY", has_api_key,
               "Configured" if has_api_key else "NOT SET — no API calls possible")
    all_ok = all_ok and ok

    # 2. ASAAS_USE_SANDBOX
    is_sandbox = settings.ASAAS_USE_SANDBOX
    check("ASAAS_USE_SANDBOX", not is_sandbox,
          "False (production mode)" if not is_sandbox else "True (SANDBOX) — change to False in Render for production")

    # 3. ASAAS_OPERATION_KEY
    has_op_key = bool(settings.ASAAS_OPERATION_KEY)
    ok = check("ASAAS_OPERATION_KEY", has_op_key,
               "Configured — transfers will be auto-authorized" if has_op_key
               else "NOT SET — every transfer will be stuck at AWAITING_TRANSFER_AUTHORIZATION")
    all_ok = all_ok and ok

    # 4. APP_BASE_URL
    base_url = settings.APP_BASE_URL
    ok = check("APP_BASE_URL", "localhost" not in base_url,
               base_url)
    all_ok = all_ok and ok

    # 5. Connectivity check against Asaas API
    print()
    print("  Connectivity:")
    if has_api_key:
        try:
            env_url = "https://sandbox.asaas.com/api/v3" if is_sandbox else "https://api.asaas.com/v3"
            resp = httpx.get(
                f"{env_url}/myAccount",
                headers={"access_token": settings.ASAAS_API_KEY},
                timeout=10.0
            )
            if resp.status_code == 200:
                data = resp.json()
                account_name = data.get("name") or data.get("tradingName") or "unknown"
                cpf_cnpj = data.get("cpfCnpj") or "***"
                check("Asaas API reachable", True,
                      f"Account: {account_name} | CNPJ/CPF: ***{cpf_cnpj[-4:]}")
            else:
                check("Asaas API reachable", False,
                      f"HTTP {resp.status_code} — check ASAAS_API_KEY and ASAAS_USE_SANDBOX")
                all_ok = False
        except Exception as e:
            check("Asaas API reachable", False, f"Connection error: {str(e)[:80]}")
            all_ok = False
    else:
        check("Asaas API reachable", False, "Skipped — ASAAS_API_KEY not set")
        all_ok = False

    # 6. Withdrawal validation webhook URL
    print()
    print("  Withdrawal Validation Webhook:")
    webhook_url = f"{base_url.rstrip('/')}/pix/webhook/asaas/validacao-saque"
    print(f"    URL to register in Asaas: {webhook_url}")
    print(f"    Path: Asaas > Mecanismos de seguranca > Validacao de saque > URL do Webhook")

    # 7. Summary and action plan
    print()
    print(SEPARATOR)
    if all_ok:
        print("  STATUS: All checks passed. Automatic authorization is active.")
    else:
        print("  STATUS: Action required:")
        print()
        if not has_op_key:
            print("  [1] Get ASAAS_OPERATION_KEY:")
            print("      Asaas Dashboard > Configuracoes > Seguranca > Chave de Operacao da API")
            print("      Copy the key and add to Render: ASAAS_OPERATION_KEY = <value>")
            print()
        if is_sandbox:
            print("  [2] Disable sandbox in Render:")
            print("      ASAAS_USE_SANDBOX = False")
            print()
        print("  [3] Register withdrawal validation webhook in Asaas (if not done):")
        print(f"      URL: {webhook_url}")
        print("      Path: Asaas > Mecanismos de seguranca > Validacao de saque")
        print("      Click: Habilitar validacao")
    print(SEPARATOR)
    print()

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
