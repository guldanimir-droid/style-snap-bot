import aiohttp
import base64
import json
import logging
import asyncio
import uuid
import time
from io import BytesIO

logger = logging.getLogger(__name__)

class GigaChatClientWrapper:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.auth_key = client_secret
        self.access_token = None
        self.token_expiry = 0
        self.token_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        self.api_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        self.files_url = "https://gigachat.devices.sberbank.ru/api/v1/files"
        self.timeout = aiohttp.ClientTimeout(total=60)
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

    async def _upload_file(self, file_bytes: bytes, filename: str = "image.jpg") -> str:
        token = await self._get_token()
        data = aiohttp.FormData()
        data.add_field('file', file_bytes, filename=filename, content_type='image/jpeg')
        data.add_field('purpose', 'general')   # обязательный параметр
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(self.files_url, headers=headers, data=data, ssl=self.ssl_context) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"File upload failed: status={resp.status}, body={error_text}")
                    raise Exception(f"File upload error {resp.status}: {error_text}")
                result = await resp.json()
                file_id = result.get("id")
                if not file_id:
                    raise Exception("No file_id in response")
                logger.info(f"File uploaded, id={file_id}")
                return file_id

    async def analyze_style(self, image_bytes: bytes, system_prompt: str) -> str:
        file_id = await self._upload_file(image_bytes, filename="style.jpg")
        token = await self._get_token()
        payload = {
            "model": "GigaChat-2-Pro",
            "messages": [
                {
                    "role": "user",
                    "content": system_prompt,
                    "attachments": [
                        {
                            "type": "file",
                            "file_id": file_id
                        }
                    ]
                }
            ],
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

    async def generate_text(self, prompt: str, system_prompt: str = None) -> str:
        token = await self._get_token()
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": "GigaChat-2-Pro",
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
