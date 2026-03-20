import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, LOG_LEVEL, SUPABASE_URL, SUPABASE_KEY, OPENWEATHER_API_KEY
from gemini_client import GeminiClientWrapper
from prompts import SYSTEM_PROMPT
from weather_api import get_weather
from affiliate import generate_affiliate_links
import database

logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), "INFO"))
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

gemini = GeminiClientWrapper(api_key=GEMINI_API_KEY)

# ---- Клавиатуры (reply-клавиатуры, без изменений) ----
def get_gender_keyboard():
    kb = [
        [KeyboardButton(text="Девушка"), KeyboardButton(text="Парень")],
        [KeyboardButton(text="Пропустить")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_style_keyboard():
    kb = [
        [KeyboardButton(text="Повседневный"), KeyboardButton(text="Деловой")],
        [KeyboardButton(text="Романтичный"), KeyboardButton(text="Спортивный")],
        [KeyboardButton(text="Пропустить")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_city_keyboard():
    kb = [
        [KeyboardButton(text="Москва"), KeyboardButton(text="Санкт-Петербург")],
        [KeyboardButton(text="Казань"), KeyboardButton(text="Екатеринбург")],
        [KeyboardButton(text="Новосибирск"), KeyboardButton(text="Владивосток")],
        [KeyboardButton(text="Калининград"), KeyboardButton(text="Другой город...")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_main_keyboard():
    kb = [
        [KeyboardButton(text="📸 Анализировать"), KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="🌆 Сменить город"), KeyboardButton(text="ℹ️ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_category_keyboard():
    kb = [
        [KeyboardButton(text="Верх"), KeyboardButton(text="Низ")],
        [KeyboardButton(text="Обувь"), KeyboardButton(text="Аксессуар")],
        [KeyboardButton(text="Другое")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_color_keyboard():
    kb = [
        [KeyboardButton(text="Черный"), KeyboardButton(text="Белый")],
        [KeyboardButton(text="Серый"), KeyboardButton(text="Синий")],
        [KeyboardButton(text="Красный"), KeyboardButton(text="Зеленый")],
        [KeyboardButton(text="Другой")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

# ---- Inline-клавиатуры ----
def get_result_keyboard():
    """Клавиатура под результатом анализа"""
    buttons = [
        [InlineKeyboardButton(text="🔄 Ещё совет", callback_data="more_advice")],
        [InlineKeyboardButton(text="📤 Поделиться", callback_data="share_result")],
        [InlineKeyboardButton(text="➕ В гардероб", callback_data="add_to_wardrobe")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---- FSM для добавления вещи (без изменений) ----
class AddItemStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_category = State()
    waiting_for_color = State()
    waiting_for_photo = State()

# ---- Обработчики команд (без изменений) ----
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    logger.info(f"Start command from user {user_id}")
    await state.clear()
    try:
        user = database.get_user(user_id)
        logger.info(f"User data: {user}")

        if not user.get("gender") or not user.get("style_preference"):
            await message.answer(
                "Привет! Я стилист на базе ИИ. Чтобы советы были точнее, ответь на пару вопросов.\n\n"
                "Ты парень или девушка?",
                reply_markup=get_gender_keyboard()
            )
        else:
            if not user.get("city"):
                await message.answer(
                    "Укажи город, в котором ты чаще всего бываешь. "
                    "Это нужно, чтобы я мог учитывать погоду в советах.\n\n"
                    "Выбери из списка или нажми «Другой город...», чтобы ввести название вручную:",
                    reply_markup=get_city_keyboard()
                )
            else:
                await message.answer(
                    "Привет! Я стилист на базе ИИ. Отправь мне своё фото в полный рост, "
                    "и я оценю твой образ, дам советы и рекомендации с учётом трендов 2026 и российской погоды.",
                    reply_markup=get_main_keyboard()
                )
    except Exception as e:
        logger.exception(f"Error in start handler: {e}")
        await message.answer("Произошла внутренняя ошибка. Попробуй позже.")

@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    user_id = str(message.from_user.id)
    user = database.get_user(user_id)
    await message.answer(
        f"👤 **Твой профиль**\n"
        f"• Пол: {user.get('gender', 'не указан')}\n"
        f"• Стиль: {user.get('style_preference', 'не указан')}\n"
        f"• Город: {user.get('city', 'не указан')}\n"
        f"• Сегодня использовано запросов: {user.get('requests_today', 0)}/3",
        parse_mode="Markdown"
    )

@dp.message(Command("setcity"))
async def cmd_setcity(message: Message):
    await message.answer(
        "В каком городе ты сейчас находишься?",
        reply_markup=get_city_keyboard()
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Я — стилист на базе ИИ. Отправь мне фото, и я оценю твой образ, дам советы и рекомендации с учётом трендов 2026 и погоды в твоём городе.\n\n"
        "**Команды:**\n"
        "/start — начать заново\n"
        "/profile — мой профиль\n"
        "/setcity — сменить город\n"
        "/additem — добавить вещь в гардероб\n"
        "/wardrobe — показать мои вещи\n"
        "/outfit — составить образ из моих вещей\n"
        "/help — эта справка",
        parse_mode="Markdown"
    )

@dp.message(Command("additem"))
async def cmd_additem(message: Message, state: FSMContext):
    await state.set_state(AddItemStates.waiting_for_name)
    await message.answer(
        "Добавляем вещь в гардероб. Напиши название (например, 'свитер', 'джинсы'):",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(AddItemStates.waiting_for_name)
async def add_item_name(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, введи название текстом.")
        return
    await state.update_data(item_name=message.text)
    await state.set_state(AddItemStates.waiting_for_category)
    await message.answer("Выбери категорию:", reply_markup=get_category_keyboard())

@dp.message(AddItemStates.waiting_for_category)
async def add_item_category(message: Message, state: FSMContext):
    if message.text not in ["Верх", "Низ", "Обувь", "Аксессуар", "Другое"]:
        await message.answer("Пожалуйста, выбери категорию из кнопок.")
        return
    await state.update_data(category=message.text)
    await state.set_state(AddItemStates.waiting_for_color)
    await message.answer("Выбери цвет:", reply_markup=get_color_keyboard())

@dp.message(AddItemStates.waiting_for_color)
async def add_item_color(message: Message, state: FSMContext):
    color = message.text
    if color not in ["Черный", "Белый", "Серый", "Синий", "Красный", "Зеленый", "Другой"]:
        await message.answer("Пожалуйста, выбери цвет из кнопок.")
        return
    if color == "Другой":
        await state.update_data(color="не указан")
    else:
        await state.update_data(color=color)
    await state.set_state(AddItemStates.waiting_for_photo)
    await message.answer("Теперь отправь фото этой вещи (можно пропустить, нажав /skip).", reply_markup=ReplyKeyboardRemove())

@dp.message(Command("skip"))
async def skip_photo(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    data = await state.get_data()
    database.add_wardrobe_item(
        user_id=user_id,
        item_name=data.get("item_name"),
        category=data.get("category"),
        color=data.get("color")
    )
    await state.clear()
    await message.answer(f"✅ Вещь «{data.get('item_name')}» добавлена в гардероб! Чтобы добавить ещё, используй /additem.")

@dp.message(AddItemStates.waiting_for_photo)
async def add_item_photo(message: Message, state: FSMContext):
    if not message.photo:
        await message.answer("Отправь фото вещи (или /skip, чтобы пропустить).")
        return
    user_id = str(message.from_user.id)
    data = await state.get_data()
    database.add_wardrobe_item(
        user_id=user_id,
        item_name=data.get("item_name"),
        category=data.get("category"),
        color=data.get("color"),
        image_url=""
    )
    await state.clear()
    await message.answer(f"✅ Вещь «{data.get('item_name')}» добавлена в гардероб с фото!", reply_markup=get_main_keyboard())

@dp.message(Command("wardrobe"))
async def cmd_wardrobe(message: Message):
    user_id = str(message.from_user.id)
    items = database.get_user_wardrobe(user_id)
    if not items:
        await message.answer("Твой гардероб пока пуст. Добавь вещи через /additem.")
        return
    text = "👕 *Твой гардероб:*\n"
    for idx, item in enumerate(items, 1):
        text += f"{idx}. {item.get('item_name')} ({item.get('category', 'нет категории')}, {item.get('color', 'нет цвета')})\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("outfit"))
async def cmd_outfit(message: Message):
    user_id = str(message.from_user.id)
    items = database.get_user_wardrobe(user_id)
    if not items:
        await message.answer("У тебя пока нет вещей в гардеробе. Добавь через /additem.")
        return

    items_text = "\n".join([f"- {item['item_name']} ({item.get('category', '?')}, {item.get('color', '?')})" for item in items])
    prompt = f"""У меня есть следующие вещи в гардеробе:
{items_text}

Составь 2-3 варианта образов из этих вещей (можно использовать некоторые вещи не обязательно все). Для каждого варианта дай краткое описание и совет, куда можно пойти в таком образе. Учитывай текущую погоду (если передана)."""

    user = database.get_user(user_id)
    city = user.get("city", "Москва")
    weather_info = await get_weather(city)
    if weather_info:
        prompt += f"\n\nСейчас в городе {city} такая погода: {weather_info}."

    await message.answer("✨ Составляю образы из твоих вещей... Это займёт несколько секунд.")

    try:
        # Временно заглушка, позже заменим на реальный вызов
        await message.answer("Функция в разработке. Скоро здесь будут готовые образы!")
    except Exception as e:
        logger.exception(f"Error generating outfit: {e}")
        await message.answer("Не удалось составить образ. Попробуй позже.")

# ---- Обработчики кнопок главного меню (без изменений) ----
@dp.message(F.text == "📸 Анализировать")
async def main_analyze(message: Message):
    await message.answer(
        "Отправь мне фото в полный рост, и я оценю твой образ!",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(F.text == "👤 Мой профиль")
async def main_profile(message: Message):
    user_id = str(message.from_user.id)
    user = database.get_user(user_id)
    await message.answer(
        f"👤 **Твой профиль**\n"
        f"• Пол: {user.get('gender', 'не указан')}\n"
        f"• Стиль: {user.get('style_preference', 'не указан')}\n"
        f"• Город: {user.get('city', 'не указан')}\n"
        f"• Сегодня использовано запросов: {user.get('requests_today', 0)}/3",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "🌆 Сменить город")
async def main_change_city(message: Message):
    await message.answer(
        "Выбери новый город:",
        reply_markup=get_city_keyboard()
    )

@dp.message(F.text == "ℹ️ Помощь")
async def main_help(message: Message):
    await message.answer(
        "Я — стилист на базе ИИ. Отправь мне фото, и я оценю твой образ, дам советы и рекомендации с учётом трендов 2026 и погоды в твоём городе.\n\n"
        "**Команды:**\n"
        "/start — начать заново\n"
        "/profile — мой профиль\n"
        "/setcity — сменить город\n"
        "/additem — добавить вещь в гардероб\n"
        "/wardrobe — показать мои вещи\n"
        "/outfit — составить образ из моих вещей\n"
        "/help — эта справка",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

# ---- Обработчики выбора пола, стиля, города (без изменений) ----
@dp.message(F.text.in_(["Девушка", "Парень"]))
async def set_gender(message: Message):
    user_id = str(message.from_user.id)
    gender = message.text
    database.set_user_info(user_id, gender=gender)
    await message.answer(
        "Отлично! А какой стиль тебе ближе?",
        reply_markup=get_style_keyboard()
    )

@dp.message(F.text.in_(["Повседневный", "Деловой", "Романтичный", "Спортивный"]))
async def set_style(message: Message):
    user_id = str(message.from_user.id)
    style = message.text
    database.set_user_info(user_id, style=style)
    await message.answer(
        "Теперь укажи город, в котором ты чаще всего бываешь.\n\n"
        "Выбери из списка или нажми «Другой город...», чтобы ввести название вручную:",
        reply_markup=get_city_keyboard()
    )

@dp.message(F.text == "Пропустить")
async def skip_info(message: Message):
    user_id = str(message.from_user.id)
    user = database.get_user(user_id)
    if not user.get("city"):
        await message.answer(
            "Укажи хотя бы город, чтобы я мог учитывать погоду.",
            reply_markup=get_city_keyboard()
        )
    else:
        await message.answer(
            "Хорошо, если захочешь заполнить позже — просто напиши /start. А пока отправь фото!",
            reply_markup=get_main_keyboard()
        )

@dp.message(F.text.in_(["Москва", "Санкт-Петербург", "Казань", "Екатеринбург", "Новосибирск", "Владивосток", "Калининград"]))
async def set_city_from_button(message: Message):
    user_id = str(message.from_user.id)
    city = message.text
    database.set_user_info(user_id, city=city)
    await message.answer(
        f"Отлично, запомнил: {city}. Теперь отправь мне фото, и я проанализирую образ с учётом погоды в твоём городе!",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "Другой город...")
async def ask_manual_city(message: Message):
    await message.answer(
        "Напиши название своего города (например, Самара):",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(F.text)
async def handle_manual_city(message: Message):
    user_id = str(message.from_user.id)
    if message.text.startswith('/'):
        return
    if message.text in ["📸 Анализировать", "👤 Мой профиль", "🌆 Сменить город", "ℹ️ Помощь"]:
        return
    user = database.get_user(user_id)
    if user.get("city") is None:
        city = message.text
        database.set_user_info(user_id, city=city)
        await message.answer(
            f"Запомнил: {city}. Теперь отправь фото, и я проанализирую образ с учётом погоды!",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(
            "Я тебя не совсем понял. Если хочешь изменить город, воспользуйся командой /setcity или кнопкой «Сменить город».",
            reply_markup=get_main_keyboard()
        )

# ---- Обработчик фото (с добавлением inline-кнопок) ----
@dp.message(F.photo)
async def handle_photo(message: Message):
    user_id = str(message.from_user.id)
    logger.info(f"Photo handler called for user {user_id}")

    DEVELOPER_ID = "8374306844"
    if user_id != DEVELOPER_ID:
        if not database.can_request(user_id, limit=3):
            await message.reply(
                "❌ Ты сегодня уже проанализировал(а) 3 образа. Хочешь ещё? "
                "Оформи подписку всего за 250₽/мес — и никаких лимитов! "
                "Пока это можно сделать, написав @твой_контакт (временно)."
            )
            return

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_path = file.file_path
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"

    await message.reply("✨ Анализирую ваш образ... Это займёт несколько секунд.")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                if resp.status != 200:
                    await message.reply("Не удалось загрузить фото. Попробуйте ещё раз.")
                    return
                image_bytes = await resp.read()

        user = database.get_user(user_id)
        gender = user.get("gender", "")
        style = user.get("style_preference", "")
        city = user.get("city", "Москва")

        weather_info = await get_weather(city)
        if weather_info:
            weather_context = (
                f"Сейчас в городе {city} такая погода: {weather_info}. "
                f"Обязательно учитывай эти погодные условия, когда будешь давать советы: "
                f"если холодно – рекомендуй тёплую одежду, если жарко – лёгкую, если дождь – непромокаемую."
            )
        else:
            weather_context = ""

        personal_prompt = SYSTEM_PROMPT
        if gender:
            personal_prompt += f"\nПользователь: {gender}."
        if style:
            personal_prompt += f"\nПредпочитаемый стиль: {style}."
        if weather_context:
            personal_prompt += f"\n\n{weather_context}"

        result = await gemini.analyze_style(image_bytes, personal_prompt)
        result_with_links = generate_affiliate_links(result)

        # Отправляем результат с inline-клавиатурой
        await message.reply(
            result_with_links,
            reply_markup=get_result_keyboard(),
            parse_mode="HTML"  # можно использовать Markdown, но ссылки и так есть
        )

        database.increment_requests(user_id)

    except Exception as e:
        logger.exception("Ошибка обработки фото: %s", e)
        await message.reply(
            "Не удалось проанализировать фото. Пожалуйста, отправьте другое, более чёткое изображение в полный рост.",
            reply_markup=get_main_keyboard()
        )

# ---- Обработчики inline-кнопок ----
@dp.callback_query(lambda c: c.data == "more_advice")
async def more_advice_callback(callback: CallbackQuery):
    await callback.answer("Советую отправить новое фото для анализа!", show_alert=False)
    await callback.message.answer("📸 Отправь мне другое фото, и я снова проанализирую твой образ.")
    await callback.message.delete()  # удаляем сообщение с кнопками (чтобы не мешало)

@dp.callback_query(lambda c: c.data == "share_result")
async def share_result_callback(callback: CallbackQuery):
    # Копируем текст последнего сообщения (или генерируем ссылку на пост)
    # Упрощённо: копируем текст ответа бота
    text = callback.message.text
    # Можно сформировать текст для публикации
    await callback.answer("Текст скопирован!", show_alert=False)
    # Отправляем сообщение с текстом для копирования
    await callback.message.answer(
        "📤 *Результат для публикации:*\n"
        f"{text}\n\n"
        "Скопируйте текст и поделитесь с друзьями!",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "add_to_wardrobe")
async def add_to_wardrobe_callback(callback: CallbackQuery):
    # Парсить текст на наличие названий вещей сложно, для простоты предложим добавить через команду
    await callback.answer("Добавление в гардероб", show_alert=False)
    await callback.message.answer(
        "➕ Чтобы добавить вещь в гардероб, используй команду `/additem`.\n"
        "Например: `/additem` → затем введи название, категорию и цвет."
    )

# ---- Запуск ----
async def main():
    logger.info("Main function started")
    logger.info("Bot starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
