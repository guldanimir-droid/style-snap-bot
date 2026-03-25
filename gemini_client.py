import aiohttp
import base64
import json
import os

class GeminiClientWrapper:
    def __init__(self, api_key: str = None):
        # Для HF api_key не нужен, но оставим для совместимости
        self.api_key = api_key
        self.hf_token = os.environ.get("HF_TOKEN")
        # Используем мультимодальную модель Qwen2-VL-7B (бесплатно, хорошо понимает русский)
        self.model = "Qwen/Qwen2-VL-7B-Instruct"

    async def analyze_style(self, image_bytes: bytes, system_prompt: str) -> str:
        if not self.hf_token:
            raise Exception("HF_TOKEN not set in environment variables")

        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        data_url = f"data:image/jpeg;base64,{img_base64}"

        # Формируем запрос для HF Inference API
        payload = {
            "inputs": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": system_prompt}
                    ]
                }
            ]
        }

        headers = {
            "Authorization": f"Bearer {self.hf_token}",
            "Content-Type": "application/json"
        }

        url = f"https://api-inference.huggingface.co/models/{self.model}"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Извлекаем текст ответа
                    try:
                        return data["choices"][0]["message"]["content"]
                    except (KeyError, IndexError):
                        return str(data)
                elif resp.status == 503:
                    # Модель загружается
                    await asyncio.sleep(5)
                    return await self.analyze_style(image_bytes, system_prompt)
                else:
                    error_text = await resp.text()
                    raise Exception(f"HF API error {resp.status}: {error_text}")
