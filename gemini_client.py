import base64
import google.generativeai as genai

class GeminiClientWrapper:
    def __init__(self, api_key: str):
        self.api_key = api_key
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')

    async def analyze_style(self, image_bytes: bytes, system_prompt: str) -> str:
        try:
            img_base64 = base64.b64encode(image_bytes).decode('utf-8')
            response = self.model.generate_content([
                system_prompt,
                {"mime_type": "image/jpeg", "data": img_base64}
            ])
            return response.text
        except Exception as e:
            raise Exception(f"Gemini API error: {e}")
