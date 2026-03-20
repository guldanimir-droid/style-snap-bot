import io
from PIL import Image, ImageDraw, ImageFont
import textwrap

def create_result_image(text: str, width: int = 800, max_height: int = 2000) -> bytes:
    """
    Создаёт изображение с текстом для публикации.
    Возвращает байты PNG.
    """
    # Параметры
    bg_color = (245, 245, 245)   # светло-серый
    text_color = (0, 0, 0)
    font_size = 18
    padding = 20
    line_height = 24

    # Подбираем шрифт (используем дефолтный, если arial нет)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.load_default()

    # Разбиваем текст на строки с переносами
    lines = []
    for line in text.split('\n'):
        if line.strip():
            wrapped = textwrap.wrap(line, width=60)  # примерно 60 символов в строке
            lines.extend(wrapped)
        else:
            lines.append('')  # сохраняем пустые строки

    # Вычисляем высоту
    text_height = len(lines) * line_height
    image_height = min(text_height + padding * 2, max_height)

    # Создаём изображение
    img = Image.new('RGB', (width, image_height), color=bg_color)
    draw = ImageDraw.Draw(img)

    y = padding
    for line in lines:
        draw.text((padding, y), line, fill=text_color, font=font)
        y += line_height

    # Сохраняем в байты
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes.getvalue()
