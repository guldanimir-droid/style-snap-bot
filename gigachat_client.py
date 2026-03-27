import aiohttp
import base64
import json
import logging
import asyncio
import ssl

logger = logging.getLogger(__name__)

class GigaChatClientWrapper:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expiry = 0
        self.token_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        self.api_url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        # Создаём SSL-контекст, который не проверяет сертификат
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    async def _get_token(self):
        """Получить OAuth2 токен (client credentials)."""
        if self.access_token and asyncio.get_event_loop().time() < self.token_expiry:
            return self.access_token

        payload = {
            "scope": "GIGACHAT_API_PERS"
        }
        auth = aiohttp.BasicAuth(self.client_id, self.client_secret)

        # Используем connector с отключённой проверкой SSL
        connector = aiohttp.TCPConnector(ssl=self.ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(self.token_url, data=payload, auth=auth) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"GigaChat token error {resp.status}: {error_text}")
                data = await resp.json()
                self.access_token = data["access_token"]
                # expires_in — секунды до истечения, установим запас 60 сек
                self.token_expiry = asyncio.get_event_loop().time() + data["expires_in"] - 60
                return self.access_token

    async def analyze_style(self, image_bytes: bytes, system_prompt: str) -> str:
        """Анализирует фото с помощью GigaChat."""
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

        connector = aiohttp.TCPConnector(ssl=self.ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(self.api_url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"GigaChat API error {resp.status}: {error_text}")
                data = await resp.json()
                try:
                    return data["choices"][0]["message"]["content"]
                except (KeyError, IndexError) as e:
                    raise Exception(f"Unexpected GigaChat response: {data}")
