import io
import re
from PIL import Image, ImageDraw, ImageFont, ImageColor
import textwrap

def create_result_image(text: str, width: int = 800, max_height: int = 2000) -> bytes:
    """
    Создаёт изображение с текстом и выделенной оценкой.
    """
    # Парсим оценку из текста (например, "Оценка стиля: 7/10")
    score_match = re.search(r'Оценка стиля:\s*(\d+)/10', text)
    score = score_match.group(1) if score_match else "?"
    
    bg_color = (245, 245, 245)
    accent_color = (255, 100, 100)  # красный для оценки
    text_color = (0, 0, 0)
    font_size = 20
    title_font_size = 28
    padding = 20
    line_height = 28
    
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
        title_font = ImageFont.truetype("arialbd.ttf", title_font_size)
    except:
        font = ImageFont.load_default()
        title_font = font
    
    # Убираем строку с оценкой из основного текста, чтобы не дублировать
    clean_text = re.sub(r'✨\s*Оценка стиля:\s*\d+/10\s*\n?', '', text)
    clean_text = clean_text.strip()
    
    # Разбиваем на строки
    lines = []
    for line in clean_text.split('\n'):
        if line.strip():
            wrapped = textwrap.wrap(line, width=50)
            lines.extend(wrapped)
        else:
            lines.append('')
    
    # Вычисляем высоту
    text_height = len(lines) * line_height
    header_height = 120  # место под шапку с оценкой
    image_height = min(text_height + header_height + padding * 2, max_height)
    
    img = Image.new('RGB', (width, image_height), color=bg_color)
    draw = ImageDraw.Draw(img)
    
    # Рисуем шапку с оценкой
    draw.rectangle([0, 0, width, header_height], fill=accent_color)
    draw.text((width//2 - 80, 30), "Оценка стиля", fill="white", font=title_font)
    draw.text((width//2 - 40, 70), f"{score}/10", fill="white", font=ImageFont.truetype("arialbd.ttf", 48) if 'arialbd' in locals() else font)
    
    # Рисуем текст
    y = header_height + padding
    for line in lines:
        draw.text((padding, y), line, fill=text_color, font=font)
        y += line_height
    
    # Добавляем низ с призывом
    footer_text = "🤖 @stil_snap_ai_bot — твой AI-стилист"
    draw.text((width//2 - 180, image_height - 30), footer_text, fill=(150,150,150), font=font)
    
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes.getvalue()
