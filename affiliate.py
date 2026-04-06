import re
import os
import logging
from takprodam import search_products

logger = logging.getLogger(__name__)

# Словарь ключевых слов (можно расширять)
CLOTHING_KEYWORDS = {
    "футболка", "рубашка", "свитер", "водолазка", "джинсы", "брюки",
    "шорты", "юбка", "платье", "куртка", "пальто", "кепка", "обувь",
    "кроссовки", "лоферы", "туфли", "сумка", "шарф", "шапка", "перчатки"
}

def extract_keywords(text: str, limit: int = 2):
    """Извлекает из текста первые 2 ключевых слова из CLOTHING_KEYWORDS"""
    found = []
    for word in CLOTHING_KEYWORDS:
        if word in text.lower():
            found.append(word)
            if len(found) >= limit:
                break
    return found

async def add_product_links(advice_text: str) -> str:
    """
    Ищет товары по ключевым словам из текста и добавляет ссылки.
    Возвращает текст + блок с товарами.
    """
    token = os.getenv("TAKPRODAM_API_TOKEN")
    if not token:
        return advice_text + "\n\n⚠️ Поиск товаров временно недоступен."

    keywords = extract_keywords(advice_text)
    if not keywords:
        return advice_text

    products_text = "\n\n🔍 **Похожие товары:**"
    for kw in keywords:
        products = search_products(kw, token, limit=1)
        if products:
            p = products[0]
            products_text += f"\n• [{p['name']}]({p['link']})"
        else:
            products_text += f"\n• {kw} — не найдено"

    return advice_text + products_text
