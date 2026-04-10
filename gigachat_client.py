import aiohttp
import base64
import json
import logging
import asyncio
import uuid
import time

logger = logging.getLogger(__name__)

class GigaChatClientWrapper:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.auth_key = client_secret
        self.access_token = None
        self.token_expiry = 0
        self.token_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        self.api_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        self.timeout = aiohttp.ClientTimeout(total=30)
        # Отключаем проверку SSL (для самоподписанных сертификатов GigaChat)
        self.ssl_context = False

    async def _get_token(self):
        now = time.monotonic()
        if self.access_token and now < self.token_expiry:
            return self.access_token

        rq_uid = str(uuid.uuid4())
        payload = {
            "scope": "GIGACHAT_API_PERS",
            "grant_type": "client_credentials"
        }
        headers = {
            "Authorization": f"Basic {self.auth_key}",
            "RqUID": rq_uid,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        }

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(self.token_url, data=payload, headers=headers, ssl=self.ssl_context) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Token request failed: status={resp.status}, body={error_text}")
                    raise Exception(f"GigaChat token error {resp.status}: {error_text}")
                data = await resp.json()
                self.access_token = data["access_token"]
                expires_in = data.get("expires_in", 1800)
                self.token_expiry = now + expires_in - 60
                return self.access_token

    async def analyze_style(self, image_bytes: bytes, system_prompt: str) -> str:
        """
        Анализирует фото одежды с помощью мультимодальной модели GigaChat-2-Pro.
        """
        token = await self._get_token()
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        # Формируем data URL для изображения
        data_url = f"data:image/jpeg;base64,{img_base64}"

        payload = {
            "model": "GigaChat-2-Pro",  # Используем мультимодальную модель 2-го поколения
            "messages": [
                {
                    "role": "user",
                    "content": system_prompt,
                    "attachments": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_url
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.7,
            "max_tokens": 1500  # Увеличил, чтобы ответ был полным
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(self.api_url, json=payload, headers=headers, ssl=self.ssl_context) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"GigaChat API error {resp.status}: {error_text}")
                    raise Exception(f"GigaChat API error {resp.status}: {error_text}")
                data = await resp.json()
                try:
                    return data["choices"][0]["message"]["content"]
                except (KeyError, IndexError) as e:
                    raise Exception(f"Unexpected GigaChat response: {data}")

    async def generate_text(self, prompt: str, system_prompt: str = None) -> str:
        """
        Генерация текстового ответа (без изображения) – для текстовых консультаций.
        """
        token = await self._get_token()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "GigaChat-2-Pro",  # И здесь тоже лучше использовать современную модель
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1500
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(self.api_url, json=payload, headers=headers, ssl=self.ssl_context) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"GigaChat API error {resp.status}: {error_text}")
                    raise Exception(f"GigaChat API error {resp.status}: {error_text}")
                data = await resp.json()
                try:
                    return data["choices"][0]["message"]["content"]
                except (KeyError, IndexError) as e:
                    raise Exception(f"Unexpected GigaChat response: {data}")
