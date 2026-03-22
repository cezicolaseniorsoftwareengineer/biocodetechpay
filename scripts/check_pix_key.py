"""
Diagnostic script: discover the correct PIX EVP key registered in BACEN DICT
for this platform's Asaas account.

Usage:
    python scripts/check_pix_key.py

The script queries the Asaas API to list all registered PIX address keys and
compares them against the hardcoded fallback UUID used by the application.

Output includes:
  - Environment: sandbox or production
  - Registered PIX keys (type + value)
  - Whether the current PLATFORM_PIX_KEY matches a registered key
  - The recommended value to set as PLATFORM_PIX_KEY in Render Dashboard

After identifying the correct key, configure it in the Render Dashboard:
    Render Dashboard > BioCodeTechPay > Environment > PLATFORM_PIX_KEY = <uuid>

The application will pick it up on the next deploy/restart and embed the
correct key in all deposit QR codes.
"""
import os
import sys

# Resolve project root relative to this script's location
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

try:
    from app.core.config import settings
except Exception as exc:
    print(f"ERROR: Could not load app settings: {exc}")
    print("Make sure you are running from the project root with the .env file present.")
    sys.exit(1)

_FALLBACK_KEY = "1a923d7b-3230-46d4-a670-87bf7ee54817"
_CURRENT_KEY  = settings.PLATFORM_PIX_KEY or _FALLBACK_KEY

_ENV  = "sandbox" if settings.ASAAS_USE_SANDBOX else "production"
_BASE = (
    "https://sandbox.asaas.com/api/v3"
    if settings.ASAAS_USE_SANDBOX
    else "https://api.asaas.com/v3"
)


def _header() -> dict:
    return {
        "access_token": settings.ASAAS_API_KEY or "",
        "User-Agent": "BioCodeTechPay-Diagnostic/1.0",
    }


def _check_api_key() -> bool:
    if not settings.ASAAS_API_KEY:
        print("ERROR: ASAAS_API_KEY is not configured in .env or environment.")
        return False
    key = settings.ASAAS_API_KEY
    if not key.startswith("$aact_"):
        print(f"WARNING: ASAAS_API_KEY does not start with $aact_ (found: {key[:8]}...)")
    mode = "sandbox" if "sandbox" in key else "prod" if "prod" in key else "unknown"
    print(f"  ASAAS_API_KEY  : present (mode hint: {mode})")
    print(f"  ASAAS_USE_SANDBOX: {settings.ASAAS_USE_SANDBOX}")
    print(f"  Effective env  : {_ENV.upper()}")
    print(f"  API base URL   : {_BASE}")
    return True


def _query_account() -> dict:
    """GET /myAccount — returns main account details including pixAddressKey if available."""
    try:
        resp = httpx.get(f"{_BASE}/myAccount", headers=_header(), timeout=10.0)
        if resp.status_code == 200:
            return resp.json()
        print(f"  /myAccount returned HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        print(f"  /myAccount request failed: {type(exc).__name__}: {exc}")
    return {}


def _query_pix_keys() -> list:
    """GET /pix/addressKeys — lists all PIX keys registered for this account."""
    try:
        resp = httpx.get(f"{_BASE}/pix/addressKeys", headers=_header(), timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", []) if isinstance(data, dict) else data
        print(f"  /pix/addressKeys returned HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as exc:
        print(f"  /pix/addressKeys request failed: {type(exc).__name__}: {exc}")
    return []


def main() -> None:
    print("=" * 60)
    print("BioCodeTechPay — PIX Key Diagnostic")
    print("=" * 60)

    print("\n[1] Configuration")
    if not _check_api_key():
        sys.exit(1)

    print(f"  PLATFORM_PIX_KEY (active): {_CURRENT_KEY}")
    print(f"  Fallback key             : {_FALLBACK_KEY}")

    print("\n[2] Asaas account info (GET /myAccount)")
    account = _query_account()
    if account:
        print(f"  Name          : {account.get('name') or account.get('tradingName', '-')}")
        print(f"  Document      : {account.get('cpfCnpj', '-')}")
        print(f"  Wallet ID     : {account.get('walletId') or account.get('id', '-')}")
        pix_key_field = account.get("pixAddressKey") or account.get("pixKey")
        if pix_key_field:
            print(f"  pixAddressKey : {pix_key_field}")
    else:
        print("  Could not retrieve account info.")

    print("\n[3] Registered PIX address keys (GET /pix/addressKeys)")
    keys = _query_pix_keys()
    if not keys:
        print("  No PIX keys found or endpoint unavailable.")
    else:
        evp_candidates = []
        for k in keys:
            key_type  = k.get("type", "?")
            key_value = k.get("key", k.get("pixAddressKey", "?"))
            status    = k.get("status", k.get("active", "?"))
            print(f"  type={key_type:<10} status={status:<10} key={key_value}")
            if key_type.upper() in ("EVP", "RANDOM", "ALEATORIA"):
                evp_candidates.append(key_value)

    print("\n[4] Diagnosis")
    all_key_values = [
        k.get("key", k.get("pixAddressKey", "")) for k in keys
    ]
    pix_key_from_account = account.get("pixAddressKey") or account.get("pixKey")
    if pix_key_from_account:
        all_key_values.append(pix_key_from_account)

    all_key_values = [v.strip().lower() for v in all_key_values if v]

    current_normalized = _CURRENT_KEY.strip().lower()
    match = current_normalized in all_key_values

    if match:
        print("  OK — current PLATFORM_PIX_KEY is registered in Asaas.")
        if _ENV == "sandbox":
            print(
                "  WARNING — environment is SANDBOX. Sandbox PIX keys are NOT registered\n"
                "  in BACEN DICT. Real bank apps cannot resolve them.\n"
                "  Action required:\n"
                "    1. Switch ASAAS_USE_SANDBOX=False in Render Dashboard.\n"
                "    2. Use a production ASAAS_API_KEY ($aact_prod_...).\n"
                "    3. Re-run this script to confirm the production key."
            )
        else:
            print("  The QR code should be scannable by real bank apps.")
    else:
        print("  MISMATCH — current PLATFORM_PIX_KEY is NOT among the registered Asaas keys.")
        if all_key_values:
            print("  Registered keys found:")
            for v in all_key_values:
                print(f"    {v}")
            recommended = evp_candidates[0] if evp_candidates else all_key_values[0]
            print(
                f"\n  Recommended fix:\n"
                f"    Set in Render Dashboard: PLATFORM_PIX_KEY = {recommended}\n"
                f"    Redeploy the application."
            )
        else:
            print(
                "  Could not retrieve any registered keys from Asaas.\n"
                "  Possible causes:\n"
                "    - ASAAS_API_KEY is not valid for this environment.\n"
                "    - No PIX key registered for this Asaas account.\n"
                "  Steps:\n"
                "    1. Log in to Asaas Dashboard > Configuracoes > Chaves PIX.\n"
                "    2. Create or view the EVP (chave aleatoria) key.\n"
                "    3. Set PLATFORM_PIX_KEY in Render Dashboard with that UUID.\n"
                "    4. Ensure ASAAS_USE_SANDBOX matches your environment."
            )

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
