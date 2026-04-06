import os
import re
import logging
from admitad import get_admitad_token, generate_admitad_link

logger = logging.getLogger(__name__)

# Список ключевых слов (можно расширять)
KEYWORDS = [
    "футболка", "рубашка", "свитер", "водолазка", "джинсы", "брюки",
    "шорты", "юбка", "платье", "куртка", "пальто", "кепка", "обувь",
    "кроссовки", "лоферы", "туфли", "сумка", "шарф", "шапка", "перчатки"
]

# ID площадки (замените на ваш)
W_ID = "ВАШ_W_ID"  # например, "123456"

# ID партнёрской программы Wildberries (замените)
WB_C_ID = "ВАШ_C_ID_WILDBERRIES"

def generate_affiliate_links(advice_text: str) -> str:
    token = get_admitad_token()
    if not token:
        return advice_text + "\n\n⚠️ Партнёрские ссылки временно недоступны."

    # Ищем ключевые слова в тексте
    found_keywords = [kw for kw in KEYWORDS if kw in advice_text.lower()]
    if not found_keywords:
        return advice_text

    # Берём первое ключевое слово
    keyword = found_keywords[0]

    # Формируем поисковый URL на Wildberries
    search_url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={keyword.replace(' ', '%20')}"

    # Генерируем партнёрскую ссылку через Admitad
    partner_link = generate_admitad_link(search_url, W_ID, WB_C_ID, token)
    if not partner_link:
        return advice_text

    # Добавляем ссылку в конец совета
    return advice_text + f"\n\n🔗 [Найти {keyword} на Wildberries]({partner_link})"
