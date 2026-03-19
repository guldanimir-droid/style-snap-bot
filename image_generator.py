import os
import aiohttp
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

async def generate_image(prompt: str, retries: int = 2) -> Optional[bytes]:
    """
    Генерирует изображение через Hugging Face Inference API (router).
    Возвращает байты изображения или None при ошибке.
    Использует модель stabilityai/stable-diffusion-2-1.
    """
    api_token = os.environ.get("HF_TOKEN")
    if not api_token:
        logger.warning("HF_TOKEN not set")
        return None

    # Используем актуальный endpoint router
    api_url = "https://router.huggingface.co/models/stabilityai/stable-diffusion-2-1"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": prompt,
        "parameters": {
            "num_inference_steps": 25,
            "guidance_scale": 7.5
        }
    }

    logger.info(f"Calling Hugging Face API for prompt: {prompt[:50]}...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    image_bytes = await resp.read()
                    logger.info(f"Image generated successfully, size: {len(image_bytes)} bytes")
                    return image_bytes
                elif resp.status == 503:
                    # Модель загружается, пробуем через несколько секунд
                    error_data = await resp.json()
                    logger.info(f"Model loading, retrying... {error_data}")
                    if retries > 0:
                        await asyncio.sleep(5)
                        return await generate_image(prompt, retries - 1)
                    else:
                        logger.error("Model loading timeout")
                        return None
                else:
                    error_text = await resp.text()
                    logger.error(f"Hugging Face API error {resp.status}: {error_text}")
                    return None
    except Exception as e:
        logger.exception(f"Error generating image: {e}")
        return None
