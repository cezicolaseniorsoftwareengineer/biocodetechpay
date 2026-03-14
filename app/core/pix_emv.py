"""
BR Code PIX EMV helpers — BACEN specification.

Extracted from pix/router.py for reuse across router, web_routes, and link page.
Functions are stateless and side-effect-free.
"""
import urllib.parse


def crc16_ccitt(data: str) -> str:
    """
    CRC-16/CCITT-FALSE (polynomial 0x1021, init 0xFFFF).
    Required by BACEN BR Code PIX specification (section 4.1).
    Mandatory for interoperability — any PSP app validates this before querying DICT.
    """
    crc = 0xFFFF
    for byte in data.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return format(crc, "04X")


def _tlv(tag: str, value: str) -> str:
    """Encodes a single TLV field: tag(2) + length(2, zero-padded decimal) + value."""
    return f"{tag}{len(value):02d}{value}"


def build_pix_static_emv(charge_id: str, value: float) -> str:
    """
    Builds a valid BR Code PIX static EMV payload per BACEN specification.
    Uses the charge UUID as the EVP random key (field 26.01).

    The generated code is format-valid and CRC-valid — any PSP app will parse it without error.
    In production (gateway configured), Asaas charges replace this entirely with a real
    dynamic QR code registered at DICT/SPI. This fallback only applies when:
      - Asaas gateway is not configured (local/dev), OR
      - Asaas API fails for this specific request.
    """
    gui = _tlv("00", "BR.GOV.BCB.PIX")
    key = _tlv("01", charge_id)           # EVP key = charge UUID (unique per charge)
    merchant_account = _tlv("26", gui + key)

    # Field 62: Additional Data — txid max 25 chars (hyphens stripped per spec)
    txid = charge_id.replace("-", "")[:25]
    additional = _tlv("62", _tlv("05", txid))

    # Field 54: Transaction Amount — must be "10.00" decimal form, NOT "1000"
    amount_str = f"{value:.2f}"

    payload = (
        _tlv("00", "01") +               # Payload Format Indicator
        _tlv("01", "11") +               # Point of Initiation = 11 (single-use static)
        merchant_account +
        _tlv("52", "0000") +             # Merchant Category Code
        _tlv("53", "986") +              # Transaction Currency: BRL = 986
        _tlv("54", amount_str) +         # Transaction Amount
        _tlv("58", "BR") +               # Country Code
        _tlv("59", "BioCodeTechPay") +   # Merchant Name (max 25 chars)
        _tlv("60", "BRASILIA") +         # Merchant City (max 15 chars)
        additional +
        "6304"                           # CRC tag — checksum appended immediately below
    )

    return payload + crc16_ccitt(payload)


def build_qr_url(emv_payload: str, size: int = 400) -> str:
    """
    Returns the qrserver.com URL for rendering the EMV QR code image.

    Parameters chosen for BR Code / PIX interoperability with POS terminals:
    - size=400x400: sufficient pixel density for maquininha scanners at arm's length
    - ecc=H: error correction level H (30%), required by BACEN for PIX QR codes
    - margin=4: quiet zone of 4 modules minimum per ISO/IEC 18004 and BR Code spec
    """
    return (
        "https://api.qrserver.com/v1/create-qr-code/"
        f"?size={size}x{size}&ecc=H&margin=4&data={urllib.parse.quote(emv_payload)}"
    )


def _walk_tlv(data: str):
    """
    Generator that yields (tag, value) pairs from a flat EMV TLV string.
    Tags are 2-char, lengths are 2-digit decimal (BR Code / PIX spec).
    Stops silently on malformed input.
    """
    pos = 0
    while pos + 4 <= len(data):
        tag = data[pos:pos + 2]
        try:
            length = int(data[pos + 2:pos + 4])
        except ValueError:
            break
        if pos + 4 + length > len(data):
            break
        yield tag, data[pos + 4:pos + 4 + length]
        pos += 4 + length


def parse_emv_pix_key(emv: str):
    """
    Extracts the Pix key and its type from EMV field 26, sub-tag 01.

    Returns (pix_key, key_type) where key_type is one of:
    EMAIL, CPF, CNPJ, PHONE, EVP.

    Returns (None, None) if the key cannot be extracted.
    """
    import re as _re

    for tag, value in _walk_tlv(emv):
        if tag == "26":
            for sub_tag, sub_val in _walk_tlv(value):
                if sub_tag == "01":
                    key = sub_val
                    if "@" in key:
                        return key, "EMAIL"
                    if _re.match(r'^\d{14}$', key):
                        return key, "CNPJ"
                    if _re.match(r'^\d{11}$', key):
                        return key, "CPF"
                    if key.startswith("+"):
                        return key, "PHONE"
                    return key, "EVP"
    return None, None


def parse_emv_amount(emv: str) -> float:
    """
    Extracts the transaction amount from EMV field 54 (Transaction Amount).
    Returns 0.0 if field 54 is absent or unparseable.
    """
    for tag, value in _walk_tlv(emv):
        if tag == "54":
            try:
                return float(value)
            except ValueError:
                return 0.0
    return 0.0
