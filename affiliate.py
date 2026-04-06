import re
import os
import requests
import logging

logger = logging.getLogger(__name__)

TAKPRODAM_API_URL = "https://api.takprodam.ru/v2/publisher/product"

def search_product(query: str, token: str):
    """Ищет первый подходящий товар по запросу и возвращает (название, ссылка) или (None, None)."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    params = {
        "search": query,
        "limit": 1
    }
    try:
        resp = requests.get(TAKPRODAM_API_URL, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = data.get('items', [])
        if items:
            item = items[0]
            return item.get('name'), item.get('link')
    except Exception as e:
        logger.error(f"Ошибка поиска товара '{query}' в Takprodam: {e}")
    return None, None

def generate_affiliate_links(advice_text: str) -> str:
    """
    Анализирует текст совета, ищет ключевые слова (названия вещей) и добавляет
    партнёрские ссылки на найденные товары через Takprodam.
    """
    token = os.getenv("TAKPRODAM_API_TOKEN")
    if not token:
        # Если токена нет, возвращаем текст без изменений
        return advice_text

    # Список ключевых слов (можно расширять)
    keywords = [
        "футболка", "рубашка", "свитер", "водолазка", "джинсы", "брюки",
        "шорты", "юбка", "платье", "куртка", "пальто", "кепка", "обувь",
        "кроссовки", "лоферы", "туфли", "сумка", "шарф", "шапка", "перчатки"
    ]

    # Ищем в тексте ключевые слова (регистронезависимо)
    found_keywords = set()
    for kw in keywords:
        if re.search(r'\b' + re.escape(kw) + r'\b', advice_text.lower()):
            found_keywords.add(kw)

    # Для каждого ключевого слова ищем товар и добавляем ссылку
    for kw in found_keywords:
        name, link = search_product(kw, token)
        if link:
            # Добавляем ссылку в конец текста (или можно вставить после упоминания)
            # Пока добавим отдельной строкой
            advice_text += f"\n\n👉 [{name or kw.capitalize()} на маркетплейсах]({link})"
        else:
            advice_text += f"\n\n🔍 По запросу «{kw}» товары не найдены."

    return advice_text
