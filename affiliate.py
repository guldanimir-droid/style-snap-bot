import re
import random

# Словарь ключевых слов и соответствующих запросов для поиска
# (можно расширять)
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
    """
    Добавляет в текст ссылки на маркетплейсы для найденных предметов одежды.
    """
    # Разбиваем текст на предложения (по точкам)
    sentences = advice_text.split('. ')
    new_sentences = []
    
    for sentence in sentences:
        new_sentence = sentence
        # Ищем в предложении ключевые слова
        for keyword, search_term in CLOTHING_KEYWORDS.items():
            if keyword in sentence.lower():
                # Генерируем ссылку на Wildberries (можно заменить на Ozon)
                # Кодируем запрос для URL
                encoded_query = search_term.replace(' ', '%20')
                wb_url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={encoded_query}"
                # Добавляем ссылку в конец предложения (если ещё не добавлена)
                if wb_url not in new_sentence:
                    # Добавляем ссылку аккуратно
                    new_sentence += f" [Найти на Wildberries]({wb_url})"
                break  # достаточно одной ссылки на предложение
        new_sentences.append(new_sentence)
    
    result = '. '.join(new_sentences)
    # Если ссылки не добавились (например, нет ключевых слов), возвращаем исходный текст
    if result == advice_text:
        # Пробуем добавить общую ссылку на поиск "модная одежда"
        result += "\n\n[Подобрать образ на Wildberries](https://www.wildberries.ru/catalog/0/search.aspx?search=модная%20одежда)"
    
    return result
