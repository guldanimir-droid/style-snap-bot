import re
import os
import logging
from admitad import get_admitad_token, generate_admitad_link

logger = logging.getLogger(__name__)

CLOTHING_KEYWORDS = {
    "футболка": "футболка",
    "рубашка": "рубашка",
    "свитер": "свитер",
    "водолазка": "водолазка",
    "джинсы": "джинсы",
    "брюки": "брюки",
    "шорты": "шорты",
    "юбка": "юбка",
    "платье": "платье",
    "куртка": "куртка",
    "пальто": "пальто",
    "кепка": "кепка",
    "обувь": "обувь",
    "кроссовки": "кроссовки",
    "лоферы": "лоферы",
    "туфли": "туфли",
    "сумка": "сумка",
    "шарф": "шарф",
    "шапка": "шапка",
    "перчатки": "перчатки"
}

# Для примера: Wildberries (c_id нужно узнать в Admitad)
WB_C_ID = "ваш_c_id_для_wildberries"   # замените
OZON_C_ID = "ваш_c_id_для_ozon"        # замените
W_ID = "ваш_w_id_площадки"             # замените

def generate_affiliate_links(advice_text: str) -> str:
    token = get_admitad_token()
    if not token:
        return advice_text + "\n\n⚠️ Партнёрские ссылки временно недоступны."

    sentences = advice_text.split('. ')
    new_sentences = []
    for sentence in sentences:
        new_sentence = sentence
        for keyword, search_term in CLOTHING_KEYWORDS.items():
            if keyword in sentence.lower():
                # Здесь нужно сформировать URL товара на маркетплейсе.
                # В реальности вы должны получить ссылку на товар из поиска или базы.
                # Для примера используем шаблон поиска Wildberries.
                product_url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={search_term.replace(' ', '%20')}"
                link = generate_admitad_link(product_url, W_ID, WB_C_ID, token)
                if link:
                    new_sentence += f" [Купить на WB]({link})"
                break
        new_sentences.append(new_sentence)
    result = '. '.join(new_sentences)
    return result
