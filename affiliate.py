import logging
from urllib.parse import quote

logger = logging.getLogger(__name__)

# === ТВОИ ПАРТНЁРСКИЕ ID ===
WILDBERRIES_PARTNER_ID = "3623509"      # из Wibes
YANDEX_MARKET_CLID = None                # заменишь позже, когда получишь
LAMODA_ADMITAD_ID = None                 # заменишь позже, когда получишь
OZON_PARTNER_ID = "0247333695"

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def generate_wb_search_url(query: str) -> str:
    encoded_query = quote(query)
    base_url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={encoded_query}"
    if WILDBERRIES_PARTNER_ID:
        return f"{base_url}&pp={WILDBERRIES_PARTNER_ID}"
    return base_url

def generate_ozon_search_url(query: str) -> str:
    encoded_query = quote(query)
    return f"https://www.ozon.ru/r/{OZON_PARTNER_ID}/?text={encoded_query}"

def generate_yandex_market_search_url(query: str) -> str:
    encoded_query = quote(query)
    base_url = f"https://market.yandex.ru/search?text={encoded_query}"
    if YANDEX_MARKET_CLID:
        return f"{base_url}&clid={YANDEX_MARKET_CLID}"
    return base_url

def generate_lamoda_search_url(query: str) -> str:
    encoded_query = quote(query)
    lamoda_direct_url = f"https://www.lamoda.ru/catalogsearch/result/?q={encoded_query}"
    if not LAMODA_ADMITAD_ID:
        return lamoda_direct_url
    from urllib.parse import quote_plus
    encoded_target = quote_plus(lamoda_direct_url)
    return f"https://ad.admitad.com/g/{LAMODA_ADMITAD_ID}/?ulp={encoded_target}"

# === ОСНОВНАЯ ФУНКЦИЯ ===

def generate_affiliate_links(advice_text: str) -> str:
    keywords = {
        "белый шарф": "белый шарф",
        "белые кеды": "белые кеды",
        "джинсовая куртка": "джинсовая куртка",
        "кожаная куртка": "кожаная куртка",
        "свитер": "свитер",
        "футболка": "футболка",
        "брюки": "брюки",
        "джинсы": "джинсы",
        "куртка": "куртка",
        "пальто": "пальто",
        "кроссовки": "кроссовки",
        "ботинки": "ботинки",
        "шапка": "шапка",
        "шарф": "шарф",
    }

    lower_text = advice_text.lower()
    for key, search_query in keywords.items():
        if key in lower_text:
            wb_link = generate_wb_search_url(search_query)
            ym_link = generate_yandex_market_search_url(search_query)
            lamoda_link = generate_lamoda_search_url(search_query)
            ozon_link = generate_ozon_search_url(search_query)
            advice_text += f"\n\n<b>Где купить {search_query}:</b>\n"
            advice_text += f"• Wildberries: {wb_link}\n"
            advice_text += f"• Яндекс Маркет: {ym_link}\n"
            advice_text += f"• Lamoda: {lamoda_link}\n"
            advice_text += f"• Ozon: {ozon_link}"
            break

    if "Где купить" not in advice_text:
        advice_text += (
            "\n\n<b>Посмотрите также на популярных маркетплейсах:</b>\n"
            f"• Wildberries: https://www.wildberries.ru\n"
            f"• Яндекс Маркет: https://market.yandex.ru\n"
            f"• Lamoda: https://www.lamoda.ru\n"
            f"• Ozon: https://www.ozon.ru"
        )
    return advice_text
