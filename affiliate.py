import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)

# TODO: замените на свои партнёрские ID после регистрации
WILDBERRIES_PARTNER_ID = "3623509"
OZON_PARTNER_ID = "0247333695"

def generate_wb_search_url(query: str) -> str:
    """Генерирует ссылку на поиск Wildberries (с партнёрским ID, если он указан)"""
    encoded_query = quote(query)
    base_url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={encoded_query}"
    if WILDBERRIES_PARTNER_ID:
        return f"{base_url}&pp={WILDBERRIES_PARTNER_ID}"
    return base_url

def generate_ozon_search_url(query: str) -> str:
    """Генерирует ссылку на поиск Ozon (с партнёрским ID, если он указан)"""
    encoded_query = quote(query)
    base_url = f"https://www.ozon.ru/search/?text={encoded_query}"
    if OZON_PARTNER_ID:
        # формат для Ozon может отличаться, уточните в партнёрской программе
        return f"https://www.ozon.ru/r/{OZON_PARTNER_ID}/?text={encoded_query}"
    return base_url

def generate_affiliate_links(advice_text: str) -> str:
    """
    Анализирует текст совета и добавляет ссылки на маркетплейсы под подходящими рекомендациями.
    Пока что работает для примера: ищет фразу "белый шарф".
    Позже можно расширить список ключевых слов.
    """
    # Список ключевых слов и соответствующих запросов
    keywords = {
        "белый шарф": "белый шарф",
        "белые кеды": "белые кеды",
        "джинсовая куртка": "джинсовая куртка",
        "кожаная куртка": "кожаная куртка",
        "свитер": "свитер",
        "футболка": "футболка",
        "брюки": "брюки",
        "джинсы": "джинсы",
    }

    lower_text = advice_text.lower()
    links_added = False
    for key, search_query in keywords.items():
        if key in lower_text:
            wb_link = generate_wb_search_url(search_query)
            ozon_link = generate_ozon_search_url(search_query)
            advice_text += f"\n\n**Где купить {search_query}:**\n• Wildberries: {wb_link}\n• Ozon: {ozon_link}"
            links_added = True
            break  # добавляем только один блок за раз (можно убрать break, если нужно несколько)

    if not links_added:
        # Если ничего не нашли, можно добавить общую ссылку на маркетплейсы
        advice_text += "\n\nПосмотрите также на Wildberries и Ozon: [перейти на Wildberries](https://www.wildberries.ru) | [перейти на Ozon](https://www.ozon.ru)"

    return advice_text
