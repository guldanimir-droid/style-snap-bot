import aiohttp
import os
from datetime import datetime
from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

async def upload_wardrobe_image(user_id: str, file_url: str) -> str:
    """Скачивает фото по URL и загружает в Supabase Storage, возвращает публичный URL"""
    bucket_name = "wardrobe"
    file_name = f"{user_id}_{int(datetime.now().timestamp())}.jpg"
    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            if resp.status != 200:
                return None
            image_bytes = await resp.read()
    try:
        supabase.storage.from_(bucket_name).upload(file_name, image_bytes, {"content-type": "image/jpeg"})
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_name)
        return public_url
    except Exception as e:
        print(f"Ошибка загрузки: {e}")
        return None
