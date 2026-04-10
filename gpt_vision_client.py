import aiohttp
import base64
import logging
import os

logger = logging.getLogger(__name__)

class GPTVisionClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is required")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def analyze_style(self, image_bytes: bytes, system_prompt: str) -> str:
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        data_url = f"data:image/jpeg;base64,{img_base64}"
        payload = {
            "model": "openai/gpt-4o-mini",  # дешёвая и быстрая модель
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": system_prompt},
                        {"type": "image_url", "image_url": {"url": data_url}}
                    ]
                }
            ],
            "max_tokens": 1500,
            "temperature": 0.7
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.base_url, json=payload, headers=self.headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"GPT Vision API error {resp.status}: {text}")
                    raise Exception(f"GPT Vision API error {resp.status}: {text}")
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    async def generate_text(self, prompt: str, system_prompt: str = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": "openai/gpt-4o-mini",
            "messages": messages,
            "max_tokens": 1500,
            "temperature": 0.7
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.base_url, json=payload, headers=self.headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"GPT Vision API error {resp.status}: {text}")
                    raise Exception(f"GPT Vision API error {resp.status}: {text}")
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
