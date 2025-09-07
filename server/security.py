import hashlib, hmac
from itsdangerous import TimestampSigner, BadSignature
from config import settings

_signer = TimestampSigner(settings.SECRET_KEY)

def make_license_key(email: str, reference: str, product_code: str) -> str:
    raw = f"{email}|{reference}|{product_code}|{settings.SECRET_KEY}"
    return hashlib.sha256(raw.encode()).hexdigest()[:40]

def sign_token(payload: str) -> str:
    return _signer.sign(payload.encode()).decode()

def unsign_token(token: str, max_age_seconds=86400*365):
    try:
        return _signer.unsign(token, max_age=max_age_seconds).decode()
    except BadSignature:
        return None

def verify_paystack_signature(body_bytes: bytes, header_signature: str) -> bool:
    if not header_signature:
        return False
    digest = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode(),
        msg=body_bytes,
        digestmod='sha512'
    ).hexdigest()
    return hmac.compare_digest(digest, header_signature)
