import aiohttp
import logging
from datetime import datetime
from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

async def upload_wardrobe_image(user_id: str, file_url: str) -> str:
    """
    Скачивает фото по URL и загружает в Supabase Storage, возвращает публичный URL.
    """
    # Укажите точное имя вашего бакета (как в Supabase)
    bucket_name = "Гардероб"   # или "wardrobe" – проверьте и исправьте

    # Генерируем уникальное имя файла
    file_name = f"{user_id}_{int(datetime.now().timestamp())}.jpg"

    try:
        # Скачиваем изображение
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                if resp.status != 200:
                    logger.error(f"Не удалось скачать фото {file_url}, статус {resp.status}")
                    return None
                image_bytes = await resp.read()

        # Загружаем в Storage
        supabase.storage.from_(bucket_name).upload(
            file_name,
            image_bytes,
            {"content-type": "image/jpeg"}
        )

        # Получаем публичную ссылку
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_name)
        logger.info(f"Фото загружено: {public_url}")
        return public_url

    except Exception as e:
        logger.error(f"Ошибка загрузки в ведро '{bucket_name}' для пользователя {user_id}: {e}")
        return None
