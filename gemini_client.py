
import aiohttp
import base64
import json

class GeminiClientWrapper:
    def __init__(self, api_key: str):
        self.api_key = api_key
        # Используем стабильную версию API v1 и модель gemini-1.5-flash
        self.base_url = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"

    async def analyze_style(self, image_bytes: bytes, system_prompt: str) -> str:
        # Кодируем изображение в base64
        img_base64 = base64.b64encode(image_bytes).decode('utf-8')

        # Формируем тело запроса
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": system_prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": img_base64
                            }
                        }
                    ]
                }
            ]
        }

        headers = {
            "Content-Type": "application/json"
        }

        url = f"{self.base_url}?key={self.api_key}"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Gemini API error {resp.status}: {error_text}")
                data = await resp.json()
                # Извлекаем текст ответа
                try:
                    text = data['candidates'][0]['content']['parts'][0]['text']
                    return text
                except (KeyError, IndexError) as e:
                    raise Exception(f"Unexpected Gemini response: {data}")
