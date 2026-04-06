import requests
import logging

logger = logging.getLogger(__name__)

TAKPRODAM_API_URL = "https://api.takprodam.ru/v2/publisher/product"

def search_products(query: str, token: str, limit: int = 5):
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
        items = data.get('items', [])
        products = []
        for item in items:
            products.append({
                "name": item.get('name', 'Без названия'),
                "link": item.get('link', '#')
            })
        return products
    except Exception as e:
        logger.error(f"Ошибка поиска Takprodam: {e}")
        return []
