import aiohttp
import base64
import json
import logging
import asyncio
import uuid  # для генерации UUID

logger = logging.getLogger(__name__)

class GigaChatClientWrapper:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expiry = 0
        self.token_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        self.api_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    async def _get_token(self):
        if self.access_token and asyncio.get_event_loop().time() < self.token_expiry:
            return self.access_token

        # Генерируем уникальный RqUID
        rq_uid = str(uuid.uuid4())

        payload = {
            "scope": "GIGACHAT_API_PERS",
            "grant_type": "client_credentials"
        }
        auth = aiohttp.BasicAuth(self.client_id, self.client_secret)

        # Заголовки: обязательно RqUID и Accept
        headers = {
            "RqUID": rq_uid,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.token_url, data=payload, auth=auth, headers=headers, ssl=False) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Token request failed: status={resp.status}, body={error_text}")
                    raise Exception(f"GigaChat token error {resp.status}: {error_text}")
                data = await resp.json()
                self.access_token = data["access_token"]
                expires_in = data.get("expires_in", 1800)  # по умолчанию 30 мин
                self.token_expiry = asyncio.get_event_loop().time() + expires_in - 60
                return self.access_token

    async def analyze_style(self, image_bytes: bytes, system_prompt: str) -> str:
        token = await self._get_token()

        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        # По документации GigaChat, изображение передаётся как base64 без префикса
        content = [
            {"type": "text", "text": system_prompt},
            {"type": "image_url", "image_url": {"url": img_base64}}
        ]

        payload = {
            "model": "GigaChat",
            "messages": [
                {
                    "role": "user",
                    "content": content
                }
            ],
            "temperature": 0.7,
            "max_tokens": 1024
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.api_url, json=payload, headers=headers, ssl=False) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"GigaChat API error {resp.status}: {error_text}")
                    raise Exception(f"GigaChat API error {resp.status}: {error_text}")
                data = await resp.json()
                try:
                    return data["choices"][0]["message"]["content"]
                except (KeyError, IndexError) as e:
                    raise Exception(f"Unexpected GigaChat response: {data}")
