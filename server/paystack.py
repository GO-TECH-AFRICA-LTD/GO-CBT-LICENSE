import requests
from config import settings

API_BASE = "https://api.paystack.co"

def verify_transaction(reference: str):
    url = f"{API_BASE}/transaction/verify/{reference}"
    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()
