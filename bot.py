import asyncio
import logging
import aiohttp
import re
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import (
    TELEGRAM_BOT_TOKEN,
    LOG_LEVEL,
    SUPABASE_URL,
    SUPABASE_KEY,
    DEVELOPER_ID,
    GIGACHAT_CLIENT_ID,
    GIGACHAT_SECRET
)

from gigachat_client import GigaChatClientWrapper
from prompts import SYSTEM_PROMPT
from affiliate import generate_affiliate_links
import database
import image_utils

logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), "INFO"))
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

gemini = GigaChatClientWrapper(
    client_id=GIGACHAT_CLIENT_ID,
    client_secret=GIGACHAT_SECRET
)

last_results = {}

def get_gender_keyboard():
    kb = [
        [KeyboardButton(text="👩 Девушка"), KeyboardButton(text="👨 Парень")],
        [KeyboardButton(text="⏩ Пропустить")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_style_keyboard():
    kb = [
        [KeyboardButton(text="👕 Повседневный"), KeyboardButton(text="💼 Деловой")],
        [KeyboardButton(text="🌸 Романтичный"), KeyboardButton(text="⚽ Спортивный")],
        [KeyboardButton(text="⏩ Пропустить")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_main_keyboard():
    kb = [
        [KeyboardButton(text="📸 Анализировать"), KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_category_keyboard():
    kb = [
        [KeyboardButton(text="🧥 Верх"), KeyboardButton(text="👖 Низ")],
        [KeyboardButton(text="👟 Обувь"), KeyboardButton(text="💍 Аксессуар")],
        [KeyboardButton(text="📦 Другое")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_color_keyboard():
    kb = [
        [KeyboardButton(text="⚫ Черный"), KeyboardButton(text="⚪ Белый")],
        [KeyboardButton(text="🌫 Серый"), KeyboardButton(text="🔵 Синий")],
        [KeyboardButton(text="🔴 Красный"), KeyboardButton(text="🟢 Зеленый")],
        [KeyboardButton(text="🎨 Другой")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_result_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🔄 Ещё совет", callback_data="more_advice")],
        [InlineKeyboardButton(text="📤 Поделиться", callback_data="share_result")],
        [InlineKeyboardButton(text="➕ В гардероб", callback_data="add_to_wardrobe")],
        [InlineKeyboardButton(text="⭐ В избранное", callback_data="save_favorite")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

class AddItemStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_category = State()
    waiting_for_color = State()
    waiting_for_photo = State()

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    logger.info(f"Start command from user {user_id}")
    await state.clear()
    if user_id in last_results:
        del last_results[user_id]
    try:
        user = database.get_user(user_id)
        logger.info(f"User data: {user}")

        if not user.get("gender") or not user.get("style_preference"):
            await message.answer(
                "🌟 <b>Привет! Я твой персональный AI-стилист!</b>\n\n"
                "Чтобы давать максимально точные советы, давай познакомимся поближе.\n"
                "Ответь на пару вопросов — это займёт всего минуту.\n\n"
                "👇 <b>Ты парень или девушка?</b>",
                parse_mode="HTML",
                reply_markup=get_gender_keyboard()
            )
        else:
            await message.answer(
                "✨ <b>Снова рад тебя видеть!</b>\n\n"
                "Отправь мне своё фото в полный рост, и я оценю твой образ, дам советы "
                "и подберу вещи с учётом трендов 2026.\n\n"
                "📸 <b>Жду фото!</b>",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
    except Exception as e:
        logger.exception(f"Error in start handler: {e}")
        await message.answer("❌ Произошла внутренняя ошибка. Попробуй позже.")

@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    user_id = str(message.from_user.id)
    user = database.get_user(user_id)
    await message.answer(
        f"👤 <b>Твой профиль</b>\n\n"
        f"• Пол: {user.get('gender', 'не указан')}\n"
        f"• Стиль: {user.get('style_preference', 'не указан')}\n"
        f"• 📊 Сегодня использовано запросов: {user.get('requests_today', 0)}/3",
        parse_mode="HTML"
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "💡 <b>Как пользоваться ботом</b>\n\n"
        "1️⃣ Отправь фото в полный рост\n"
        "2️⃣ Получи разбор образа с оценкой и советами\n"
        "3️⃣ Сохраняй понравившиеся идеи в избранное\n"
        "4️⃣ Добавляй вещи в виртуальный гардероб\n\n"
        "<b>Команды:</b>\n"
        "/start — начать заново\n"
        "/profile — мой профиль\n"
        "/additem — добавить вещь в гардероб\n"
        "/wardrobe — показать мои вещи\n"
        "/outfit — составить образ из моих вещей\n"
        "/favorites — показать сохранённые образы\n"
        "/help — эта справка",
        parse_mode="HTML"
    )

# Остальные обработчики (additem, wardrobe, outfit, favorites) остаются без изменений,
# но в них тоже можно добавить HTML-форматирование. Для краткости я их не переписываю,
# но в финальном файле они будут с улучшенным форматированием.

# ... (здесь идут все остальные обработчики, аналогично предыдущей версии)

# ---- Обработчик фото ----
@dp.message(F.photo)
async def handle_photo(message: Message):
    user_id = str(message.from_user.id)
    logger.info(f"Photo handler called for user {user_id}")

    photo = message.photo[-1]
    if photo.file_size > 5 * 1024 * 1024:
        await message.reply("⚠️ Фото слишком большое (более 5 МБ). Пожалуйста, отправьте изображение поменьше.")
        return

    if user_id != DEVELOPER_ID:
        if not database.can_request(user_id, limit=3):
            await message.reply(
                "❌ <b>Лимит исчерпан</b>\n\n"
                "Ты сегодня уже проанализировал(а) 3 образа.\n"
                "Хочешь безлимит? Оформи подписку всего за 250₽/мес!\n"
                "Пока это можно сделать, написав @твой_контакт.",
                parse_mode="HTML"
            )
            return

    file = await bot.get_file(photo.file_id)
    file_path = file.file_path
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"

    await message.reply("🔍 Анализирую ваш образ... Это займёт несколько секунд.")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                if resp.status != 200:
                    await message.reply("❌ Не удалось загрузить фото. Попробуйте ещё раз.")
                    return
                image_bytes = await resp.read()

        user = database.get_user(user_id)
        gender = user.get("gender", "")
        style = user.get("style_preference", "")

        personal_prompt = SYSTEM_PROMPT
        if gender:
            personal_prompt += f"\nПользователь: {gender}."
        if style:
            personal_prompt += f"\nПредпочитаемый стиль: {style}."

        result = await gemini.analyze_style(image_bytes, personal_prompt)
        result_with_links = generate_affiliate_links(result)

        last_results[user_id] = result_with_links

        # Отправляем результат с HTML-форматированием
        await message.reply(
            result_with_links,
            reply_markup=get_result_keyboard(),
            parse_mode="HTML"
        )

        database.increment_requests(user_id)

    except Exception as e:
        logger.exception("Ошибка обработки фото: %s", e)
        await message.reply(
            "❌ Не удалось проанализировать фото. Пожалуйста, отправьте другое, более чёткое изображение в полный рост.",
            reply_markup=get_main_keyboard()
        )

# ... (остальные inline-обработчики без изменений, но они также могут использовать HTML)

# ---- Запуск ----
async def main():
    logger.info("Main function started")
    logger.info("Bot starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
