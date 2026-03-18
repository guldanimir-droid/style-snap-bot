# affiliate.py
import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Здесь позже будут твои партнёрские ID
WILDBERRIES_PARTNER_ID = "your_wb_id"  # заменишь позже
OZON_PARTNER_ID = "your_ozon_id"       # заменишь позже

def generate_wb_search_url(query: str) -> str:
    """Генерирует ссылку на поиск Wildberries"""
    encoded_query = quote(query)
    # Базовая ссылка (без партнёрского ID)
    return f"https://www.wildberries.ru/catalog/0/search.aspx?search={encoded_query}"

def generate_ozon_search_url(query: str) -> str:
    """Генерирует ссылку на поиск Ozon"""
    encoded_query = quote(query)
    # Базовая ссылка (без партнёрского ID)
    return f"https://www.ozon.ru/search/?text={encoded_query}"

def generate_affiliate_links(advice_text: str) -> str:
    """
    Ищет в тексте совета ключевые вещи и добавляет ссылки
    """
    # Простой пример: ищем фразу "белый шарф" и добавляем ссылки
    if "белый шарф" in advice_text.lower():
        wb_link = generate_wb_search_url("белый шарф")
        ozon_link = generate_ozon_search_url("белый шарф")
        links = f"\n\nГде купить:\n• Wildberries: {wb_link}\n• Ozon: {ozon_link}"
        return advice_text + links
    
    # Если ничего не нашли, возвращаем исходный текст
    return advice_text
