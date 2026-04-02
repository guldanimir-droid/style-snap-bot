import logging

logger = logging.getLogger(__name__)

# Эта функция больше не нужна, но оставим заглушку
async def recognize_clothing(image_bytes: bytes, client) -> tuple[str, str]:
    """
    Возвращает (тип_одежды, описание)
    Теперь просто возвращает заглушку, реальные данные получим от пользователя
    """
    return "неизвестно", "требуется уточнение"
