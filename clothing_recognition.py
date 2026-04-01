import logging
from gigachat_client import GigaChatClientWrapper

logger = logging.getLogger(__name__)

async def recognize_clothing(image_bytes: bytes, client: GigaChatClientWrapper) -> tuple[str, str]:
    """
    Возвращает (тип_одежды, описание)
    """
    prompt = (
        "Ты — стилист. Определи, какой предмет одежды изображён на фото. "
        "Если на фото несколько предметов, выбери основной (тот, что лучше виден). "
        "Ответь строго в формате: тип|описание. Например: 'рубашка|синяя клетчатая рубашка'."
    )
    try:
        result = await client.analyze_style(image_bytes, prompt)
        if '|' in result:
            clothing_type, description = result.split('|', 1)
            return clothing_type.strip(), description.strip()
        else:
            return "неизвестно", result.strip()
    except Exception as e:
        logger.exception("Ошибка распознавания одежды")
        return "неизвестно", "не удалось распознать"
