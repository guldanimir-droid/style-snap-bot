import logging
import re
from gigachat_client import GigaChatClientWrapper

logger = logging.getLogger(__name__)

async def recognize_clothing(image_bytes: bytes, client: GigaChatClientWrapper) -> tuple[str, str]:
    """
    Возвращает (тип_одежды, описание)
    """
    prompt = (
        "Ты — система распознавания одежды. Твоя задача — точно определить предмет одежды на фото.\n"
        "Правила:\n"
        "- Если на фото несколько предметов, выбери самый крупный и чёткий.\n"
        "- Тип одежды должен быть одним из: футболка, рубашка, свитер, водолазка, джинсы, брюки, шорты, юбка, платье, куртка, пальто, кепка, обувь.\n"
        "- Описание: кратко укажи цвет и фактуру (например: 'чёрная трикотажная', 'синие джинсовые').\n"
        "Формат ответа строгий: тип|описание\n"
        "Примеры правильных ответов:\n"
        "брюки|серые классические\n"
        "водолазка|чёрная тонкая\n"
        "футболка|белая хлопковая\n"
        "Если не уверен, напиши: неизвестно|предмет не распознан\n"
        "Ответь строго в этом формате, без лишних слов."
    )
    try:
        result = await client.analyze_style(image_bytes, prompt)
        logger.info(f"Raw recognition result: {result}")
        
        # Проверяем формат: тип|описание
        if '|' in result:
            parts = result.split('|', 1)
            clothing_type = parts[0].strip().lower()
            description = parts[1].strip()
            
            # Нормализуем тип (приводим к одному из известных)
            known_types = ['футболка', 'рубашка', 'свитер', 'водолазка', 'джинсы', 'брюки', 'шорты', 'юбка', 'платье', 'куртка', 'пальто', 'кепка', 'обувь', 'неизвестно']
            if clothing_type not in known_types:
                # Пытаемся найти похожее слово
                for known in known_types:
                    if known in clothing_type or clothing_type in known:
                        clothing_type = known
                        break
                else:
                    clothing_type = 'неизвестно'
            
            # Если описание слишком длинное, обрезаем
            if len(description) > 100:
                description = description[:100]
            
            return clothing_type, description
        else:
            # Если нет разделителя, считаем, что это описание без типа
            return 'неизвестно', result.strip()[:100]
            
    except Exception as e:
        logger.exception("Ошибка распознавания одежды")
        return 'неизвестно', 'ошибка распознавания'
