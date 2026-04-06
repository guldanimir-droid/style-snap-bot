import re
import os
import logging
from takprodam import search_products

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

def generate_affiliate_links(advice_text: str) -> str:
    token = os.getenv("TAKPRODAM_API_TOKEN")
    if not token:
        return advice_text + "\n\n⚠️ Сервис поиска товаров временно недоступен."
    
    sentences = advice_text.split('. ')
    new_sentences = []
    for sentence in sentences:
        new_sentence = sentence
        for keyword, search_term in CLOTHING_KEYWORDS.items():
            if keyword in sentence.lower():
                products = search_products(search_term, token, limit=1)
                if products:
                    link = products[0]['link']
                    if link not in new_sentence:
                        new_sentence += f" [Купить на WB]({link})"
                break
        new_sentences.append(new_sentence)
    result = '. '.join(new_sentences)
    return result
