import requests
import logging

logger = logging.getLogger(__name__)

TAKPRODAM_API_URL = "https://api.takprodam.ru/v2/publisher/product"

def search_products(query: str, token: str, limit: int = 5):
    """
    Ищет товары на Takprodam по ключевому слову.
    Возвращает список словарей: [{"name": ..., "link": ...}, ...]
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    params = {
        "search": query,
        "limit": limit
    }
    try:
        resp = requests.get(TAKPRODAM_API_URL, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # Предполагаем, что API возвращает список в data['items']
        items = data.get('items', [])
        products = []
        for item in items:
            products.append({
                "name": item.get('name', 'Без названия'),
                "link": item.get('link', '#')
            })
        return products
    except Exception as e:
        logger.error(f"Ошибка при поиске товаров Takprodam: {e}")
        return []
