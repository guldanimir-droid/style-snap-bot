import os
import requests
from base64 import b64encode

ADMITAD_TOKEN_URL = "https://api.admitad.com/token/"
ADMITAD_DEEPLINK_URL = "https://api.admitad.com/deeplink/"

def get_admitad_token():
    client_id = os.getenv("ADMITAD_CLIENT_ID")
    client_secret = os.getenv("ADMITAD_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    auth_str = f"{client_id}:{client_secret}"
    auth_b64 = b64encode(auth_str.encode()).decode()
    headers = {
        "Authorization": f"Basic {auth_b64}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "deeplink_generator",
    }
    try:
        resp = requests.post(ADMITAD_TOKEN_URL, headers=headers, data=data, timeout=15)
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception as e:
        print(f"Admitad token error: {e}")
        return None

def generate_admitad_link(product_url: str, w_id: str, c_id: str, access_token: str) -> str:
    url = f"{ADMITAD_DEEPLINK_URL}{w_id}/advcampaign/{c_id}/"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"ulp": product_url}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data and isinstance(data, list) and len(data) > 0:
            return data[0].get("link")
        return None
    except Exception as e:
        print(f"Admitad deeplink error: {e}")
        return None
