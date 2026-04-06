import requests
import os
from base64 import b64encode

def get_admitad_token():
    # Получаем данные из переменных окружения (нужно будет добавить в Railway)
    client_id = os.getenv("ADMITAD_CLIENT_ID")
    client_secret = os.getenv("ADMITAD_CLIENT_SECRET")

    # Готовим заголовок для Basic-авторизации
    auth_string = f"{client_id}:{client_secret}"
    auth_bytes = auth_string.encode('ascii')
    auth_b64 = b64encode(auth_bytes).decode('ascii')

    headers = {
        "Authorization": f"Basic {auth_b64}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "client_credentials",
        "scope": "deeplink_generator",
    }

    try:
        response = requests.post("https://api.admitad.com/token/", headers=headers, data=data)
        response.raise_for_status()
        token_data = response.json()
        return token_data.get("access_token")
    except Exception as e:
        print(f"Ошибка при получении токена Admitad: {e}")
        return None
