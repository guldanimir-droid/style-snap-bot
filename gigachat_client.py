import aiohttp
import base64
import json
import logging
import asyncio
import uuid

logger = logging.getLogger(__name__)

class GigaChatClientWrapper:
    def __init__(self, client_id: str, client_secret: str):
        # client_id и client_secret: это client_id и ключ авторизации (закодированный)
        # Но client_secret у нас уже готов для Basic Auth, поэтому будем использовать напрямую
        self.auth_key = client_secret  # это и есть готовый Authorization key
        self.access_token = None
        self.token_expiry = 0
        self.token_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        self.api_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

    async def _get_token(self):
        if self.access_token and asyncio.get_event_loop().time() < self.token_expiry:
            return self.access_token

        payload = {
            "scope": "GIGACHAT_API_PERS",
            "grant_type": "client_credentials"
        }
        # Генерируем случайный UUID для RqUID
        rquid = str(uuid.uuid4())

        headers = {
            "Authorization": f"Basic {self.auth_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": rquid
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.token_url, data=payload, headers=headers, ssl=False) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Token request failed: status={resp.status}, body={error_text}")
                    raise Exception(f"GigaChat token error {resp.status}: {error_text}")
                data = await resp.json()
                self.access_token = data["access_token"]
                # expires_in может быть в секундах, возможно в ответе есть поле expires_at
                expires_in = data.get("expires_in", 3600)  # если нет, ставим час
                self.token_expiry = asyncio.get_event_loop().time() + expires_in - 60
                return self.access_token

    async def analyze_style(self, image_bytes: bytes, system_prompt: str) -> str:
        token = await self._get_token()

        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        data_url = f"data:image/jpeg;base64,{img_base64}"

        payload = {
            "model": "GigaChat",
            "messages": [
                {
                    "role": "user",
                    "content": system_prompt,
                    "attachments": [
                        {
                            "type": "image_url",
                            "url": data_url
                        }
                    ]
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
