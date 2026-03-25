import aiohttp
import base64
import json
import os
import asyncio

class GeminiClientWrapper:
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.hf_token = os.environ.get("HF_TOKEN")
        # Мультимодальная модель, хорошо понимает русский язык
        self.model = "Qwen/Qwen2-VL-7B-Instruct"

    async def analyze_style(self, image_bytes: bytes, system_prompt: str) -> str:
        if not self.hf_token:
            raise Exception("HF_TOKEN not set in environment variables")

        img_base64 = base64.b64encode(image_bytes).decode('utf-8')
        data_url = f"data:image/jpeg;base64,{img_base64}"

        # Формат запроса для Qwen2-VL (chat template)
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

        url = f"https://api-inference.huggingface.co/models/{self.model}"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Qwen2-VL возвращает список сообщений
                    try:
                        # Обычно ответ в data[0]['generated_text'] или data[0]['content']
                        if isinstance(data, list) and len(data) > 0:
                            if 'generated_text' in data[0]:
                                return data[0]['generated_text']
                            elif 'content' in data[0]:
                                return data[0]['content']
                        return str(data)
                    except Exception as e:
                        raise Exception(f"Unexpected HF response: {data}")
                elif resp.status == 503:
                    # Модель загружается – ждём и повторяем
                    await asyncio.sleep(5)
                    return await self.analyze_style(image_bytes, system_prompt)
                else:
                    error_text = await resp.text()
                    raise Exception(f"HF API error {resp.status}: {error_text}")
