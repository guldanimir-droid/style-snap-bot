import aiohttp
import base64
import json
import os
import asyncio

class GeminiClientWrapper:
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.hf_token = os.environ.get("HF_TOKEN")
        # Модель, поддерживающая мультимодальность
        self.model = "Qwen/Qwen2-VL-7B-Instruct"
        self.alt_model = "llava-hf/llava-1.5-7b-hf"

    async def analyze_style(self, image_bytes: bytes, system_prompt: str) -> str:
        if not self.hf_token:
            raise Exception("HF_TOKEN not set in environment variables")

        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        data_url = f"data:image/jpeg;base64,{img_base64}"

        payload = {
            "inputs": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": system_prompt}
                    ]
                }
            ],
            "parameters": {
                "max_new_tokens": 1024,
                "temperature": 0.7
            }
        }

        headers = {
            "Authorization": f"Bearer {self.hf_token}",
            "Content-Type": "application/json"
        }

        url = f"https://router.huggingface.co/models/{self.model}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if isinstance(data, list) and len(data) > 0:
                            if 'generated_text' in data[0]:
                                return data[0]['generated_text']
                            elif 'content' in data[0]:
                                return data[0]['content']
                        return str(data)
                    elif resp.status == 404:
                        # Модель не найдена – пробуем запасную
                        return await self._try_alt_model(image_bytes, system_prompt, headers)
                    elif resp.status == 503:
                        await asyncio.sleep(5)
                        return await self.analyze_style(image_bytes, system_prompt)
                    else:
                        error_text = await resp.text()
                        raise Exception(f"HF API error {resp.status}: {error_text}")
            except aiohttp.ClientError as e:
                raise Exception(f"Network error: {e}")

    async def _try_alt_model(self, image_bytes: bytes, system_prompt: str, headers: dict) -> str:
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        data_url = f"data:image/jpeg;base64,{img_base64}"

        payload = {
            "inputs": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": system_prompt}
                    ]
                }
            ],
            "parameters": {
                "max_new_tokens": 1024,
                "temperature": 0.7
            }
        }

        url = f"https://router.huggingface.co/models/{self.alt_model}"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        if 'generated_text' in data[0]:
                            return data[0]['generated_text']
                        elif 'content' in data[0]:
                            return data[0]['content']
                    return str(data)
                else:
                    error_text = await resp.text()
                    raise Exception(f"Alternative HF API error {resp.status}: {error_text}")
