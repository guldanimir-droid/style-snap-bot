import os
import aiohttp
import logging
from typing import Optional
import asyncio

logger = logging.getLogger(__name__)

async def generate_image(prompt: str, style: str = None) -> Optional[str]:
    """
    Генерирует изображение через Hugging Face Inference API (FLUX.1-schnell).
    Возвращает URL сгенерированного изображения или None при ошибке.
    
    Использует бесплатный Serverless Inference API.
    Ограничения: несколько сотен запросов в час для бесплатных аккаунтов [citation:4].
    
    Args:
        prompt: текстовое описание для генерации
        style: игнорируется (оставлено для совместимости)
    """
    api_token = os.environ.get("HF_TOKEN")
    if not api_token:
        logger.warning("HF_TOKEN not set in environment variables")
        return None

    # Используем FLUX.1-schnell через Inference API [citation:2]
    api_url = "https://router.huggingface.co/models/black-forest-labs/FLUX.1-schnell"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "inputs": prompt,
        "parameters": {
            "num_inference_steps": 25,  # оптимальное качество/скорость
            "guidance_scale": 7.5        # точность следования промпту
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    # API возвращает бинарные данные изображения
                    image_data = await resp.read()
                    
                    # Загружаем изображение во временное хранилище
                    # В Hugging Face Serverless API нет прямого URL, только бинарные данные [citation:8]
                    # Поэтому нам нужно временно сохранить изображение и получить для него URL
                    # Для простоты пока вернём None — в следующей версии добавим загрузку в облако
                    logger.info(f"Image generated successfully for prompt: {prompt[:50]}...")
                    return None  # временно, пока не реализуем загрузку в облако
                    
                elif resp.status == 503:
                    # Модель загружается — ждём и пробуем снова [citation:8]
                    logger.info("Model is loading, waiting 5 seconds...")
                    await asyncio.sleep(5)
                    return await generate_image(prompt)  # рекурсивный повтор
                    
                else:
                    error_text = await resp.text()
                    logger.error(f"Hugging Face API error {resp.status}: {error_text}")
                    return None
                    
    except Exception as e:
        logger.exception(f"Error generating image: {e}")
        return None
