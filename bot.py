import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage

from config import TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, LOG_LEVEL, SUPABASE_URL, SUPABASE_KEY, OPENWEATHER_API_KEY
from gemini_client import GeminiClientWrapper
from prompts import SYSTEM_PROMPT
from weather_api import get_weather
import database

logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), "INFO"))
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

gemini = GeminiClientWrapper(api_key=GEMINI_API_KEY)

# ---- Клавиатуры ----

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

# ---- Обработчики команд ----

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = str(message.from_user.id)
    logger.info(f"Start command from user {user_id}")
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
                    "и я оценю твой образ, дам советы и рекомендации с учётом трендов 2026 и российской погоды. Жду фото!"
                )
    except Exception as e:
        logger.exception(f"Error in start handler: {e}")
        await message.answer("Произошла внутренняя ошибка. Попробуй позже.")

@dp.message(Command("setcity"))
async def cmd_setcity(message: Message):
    await message.answer(
        "В каком городе ты сейчас находишься? (например, Москва)",
        reply_markup=get_city_keyboard()
    )

# ---- Обработчики выбора пола, стиля и города ----

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
        "Теперь укажи город, в котором ты чаще всего бываешь. "
        "Это нужно, чтобы я мог учитывать погоду в советах.\n\n"
        "Выбери из списка или нажми «Другой город...», чтобы ввести название вручную:",
        reply_markup=get_city_keyboard()
    )

@dp.message(F.text == "Пропустить")
async def skip_info(message: Message):
    await message.answer(
        "Хорошо, если захочешь заполнить позже — просто напиши /start. А пока отправь фото!",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(F.text.in_(["Москва", "Санкт-Петербург", "Казань", "Екатеринбург", "Новосибирск", "Владивосток", "Калининград"]))
async def set_city_from_button(message: Message):
    user_id = str(message.from_user.id)
    city = message.text
    database.set_user_info(user_id, city=city)
    await message.answer(
        f"Отлично, запомнил: {city}. Теперь отправь мне своё фото, и я проанализирую образ с учётом погоды в твоём городе!",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(F.text == "Другой город...")
async def ask_manual_city(message: Message):
    await message.answer(
        "Напиши название своего города (например, Самара):",
        reply_markup=ReplyKeyboardRemove()
    )

# Обработчик для ручного ввода города
@dp.message()
async def handle_manual_city(message: Message):
    user_id = str(message.from_user.id)
    if not message.text:
        return
    if message.text.startswith('/'):
        return
    user = database.get_user(user_id)
    if user.get("city") is None:
        city = message.text
        database.set_user_info(user_id, city=city)
        await message.answer(
            f"Запомнил: {city}. Теперь отправь фото, и я проанализирую образ с учётом погоды!",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await message.answer(
            "Я тебя не совсем понял. Если хочешь изменить город, воспользуйся командой /setcity."
        )

# ---- Обработчик фото ----

@dp.message(F.photo)
async def handle_photo(message: Message):
    user_id = str(message.from_user.id)

    # Твой user_id (исключение для разработчика)
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
                f"если холодно – рекомендуй тёплую одежду (куртки, свитера, непромокаемую обувь), "
                f"если жарко – лёгкую и дышащую, если дождь – непромокаемые вещи и т.д. "
                f"Пусть твои рекомендации будут практичными и соответствовать текущей погоде."
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
        await message.reply(result)

        database.increment_requests(user_id)

    except Exception as e:
        logger.exception("Ошибка обработки фото: %s", e)
        await message.reply(
            "Не удалось проанализировать фото. Пожалуйста, отправьте другое, более чёткое изображение в полный рост."
        )

# ---- Отладочный обработчик для всех сообщений ----
@dp.message()
async def debug_all_messages(message: Message):
    logger.info(f"DEBUG: Got message from {message.from_user.id}, content_type: {message.content_type}, text: {message.text}")
    if message.photo:
        logger.info("DEBUG: This message contains photo, but main handler missed it!")

# ---- Запуск ----

async def main():
    logger.info("Bot starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
