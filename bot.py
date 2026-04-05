import asyncio
import logging
import aiohttp
import json
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext

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
from cache import last_results_cache
from states import ProfileStates

logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), "INFO"))
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

gemini = GigaChatClientWrapper(
    client_id=GIGACHAT_CLIENT_ID,
    client_secret=GIGACHAT_SECRET
)

# ---- Клавиатуры ----
def get_gender_keyboard():
    kb = [[KeyboardButton(text="👩 Девушка"), KeyboardButton(text="👨 Парень")],[KeyboardButton(text="⏩ Пропустить")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_style_keyboard():
    kb = [[KeyboardButton(text="👕 Повседневный"), KeyboardButton(text="💼 Деловой")],[KeyboardButton(text="🌸 Романтичный"), KeyboardButton(text="⚽ Спортивный")],[KeyboardButton(text="⏩ Пропустить")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_figure_keyboard():
    kb = [[KeyboardButton(text="⏳ Песочные часы"), KeyboardButton(text="🍐 Груша")],[KeyboardButton(text="🍎 Яблоко"), KeyboardButton(text="📏 Прямоугольник")],[KeyboardButton(text="⏩ Пропустить")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_color_keyboard():
    kb = [[KeyboardButton(text="🌸 Весна"), KeyboardButton(text="☀️ Лето")],[KeyboardButton(text="🍂 Осень"), KeyboardButton(text="❄️ Зима")],[KeyboardButton(text="⏩ Пропустить")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_budget_keyboard():
    kb = [[KeyboardButton(text="🛍 Эконом (до 3000₽)"), KeyboardButton(text="💼 Средний (3000-10000₽)")],[KeyboardButton(text="💎 Премиум (от 10000₽)"), KeyboardButton(text="⏩ Пропустить")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_main_keyboard():
    kb = [
        [KeyboardButton(text="📸 Анализировать"), KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="🔗 Рефералка"), KeyboardButton(text="💬 Спросить стилиста")],
        [KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_result_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🔄 Ещё совет", callback_data="more_advice")],
        [InlineKeyboardButton(text="📤 Поделиться", callback_data="share_result")],
        [InlineKeyboardButton(text="⭐ В избранное", callback_data="save_favorite")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---- Проверка на безопасность ----
async def check_image_safety(image_bytes: bytes) -> bool:
    moderation_prompt = (
        "Ты — модератор. Определи, есть ли на фото обнажённая грудь, половые органы, "
        "явные сексуальные действия или порнография. "
        "Если на фото человек в обычной одежде, нижнем белье или купальнике — это безопасно. "
        "Ответь только одним словом: 'опасно' или 'безопасно'."
    )
    try:
        result = await gemini.analyze_style(image_bytes, moderation_prompt)
        return 'опасно' not in result.lower()
    except Exception as e:
        logger.error(f"Safety check failed: {e}")
        return True

# ---- Обработчики команд ----
@dp.message(CommandStart(deep_link=True))
async def cmd_start_with_ref(message: Message, command: CommandObject, state: FSMContext):
    user_id = str(message.from_user.id)
    if command.args:
        database.apply_referral(user_id, command.args)
    await cmd_start(message, state)

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    if user_id in last_results_cache:
        del last_results_cache[user_id]
    user = database.get_user(user_id)
    if not user.get("gender") or not user.get("style_preference"):
        await state.set_state(ProfileStates.waiting_gender)
        await message.answer(
            "🌟 <b>Привет! Я твой AI-стилист!</b>\n\n"
            "Давай познакомимся, чтобы я мог давать точные советы.\n"
            "Ответь на пару вопросов — это займёт минуту.\n\n"
            "👇 <b>Ты парень или девушка?</b>",
            parse_mode="HTML",
            reply_markup=get_gender_keyboard()
        )
    else:
        await message.answer(
            "✨ <b>Снова рад тебя видеть!</b>\n\n"
            "📸 Отправь своё фото — я дам совет по стилю.\n"
            "💬 Или задай текстовый вопрос о моде.\n\n"
            "Бесплатно: 3 анализа + бонусы за приглашения.\n"
            "Дополнительные анализы можно купить в профиле за Telegram Stars.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )

# ---- Полная анкета (FSM) ----
@dp.message(ProfileStates.waiting_gender, F.text.in_(["👩 Девушка", "👨 Парень"]))
async def process_gender(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    gender = message.text.split()[1]
    database.set_user_info(user_id, gender=gender)
    await state.set_state(ProfileStates.waiting_style)
    await message.answer("Отлично! А какой стиль тебе ближе?", reply_markup=get_style_keyboard())

@dp.message(ProfileStates.waiting_gender, F.text == "⏩ Пропустить")
async def skip_gender(message: Message, state: FSMContext):
    await state.set_state(ProfileStates.waiting_style)
    await message.answer("Хорошо, пропустим. А какой стиль тебе ближе?", reply_markup=get_style_keyboard())

@dp.message(ProfileStates.waiting_style, F.text.in_(["👕 Повседневный", "💼 Деловой", "🌸 Романтичный", "⚽ Спортивный"]))
async def process_style(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    style = message.text.split()[1]
    database.set_user_info(user_id, style_preference=style)
    await state.set_state(ProfileStates.waiting_figure)
    await message.answer("Какой у тебя тип фигуры?", reply_markup=get_figure_keyboard())

@dp.message(ProfileStates.waiting_style, F.text == "⏩ Пропустить")
async def skip_style(message: Message, state: FSMContext):
    await state.set_state(ProfileStates.waiting_figure)
    await message.answer("Хорошо. Какой у тебя тип фигуры?", reply_markup=get_figure_keyboard())

@dp.message(ProfileStates.waiting_figure, F.text.in_(["⏳ Песочные часы", "🍐 Груша", "🍎 Яблоко", "📏 Прямоугольник"]))
async def process_figure(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    figure = message.text.split()[1]
    database.set_user_info(user_id, figure_type=figure)
    await state.set_state(ProfileStates.waiting_color)
    await message.answer("А твой цветотип?", reply_markup=get_color_keyboard())

@dp.message(ProfileStates.waiting_figure, F.text == "⏩ Пропустить")
async def skip_figure(message: Message, state: FSMContext):
    await state.set_state(ProfileStates.waiting_color)
    await message.answer("Пропустим. А твой цветотип?", reply_markup=get_color_keyboard())

@dp.message(ProfileStates.waiting_color, F.text.in_(["🌸 Весна", "☀️ Лето", "🍂 Осень", "❄️ Зима"]))
async def process_color(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    color = message.text.split()[1]
    database.set_user_info(user_id, color_type=color)
    await state.set_state(ProfileStates.waiting_budget)
    await message.answer("Какой бюджет на одежду?", reply_markup=get_budget_keyboard())

@dp.message(ProfileStates.waiting_color, F.text == "⏩ Пропустить")
async def skip_color(message: Message, state: FSMContext):
    await state.set_state(ProfileStates.waiting_budget)
    await message.answer("Пропустим. Какой бюджет на одежду?", reply_markup=get_budget_keyboard())

@dp.message(ProfileStates.waiting_budget, F.text.in_(["🛍 Эконом (до 3000₽)", "💼 Средний (3000-10000₽)", "💎 Премиум (от 10000₽)"]))
async def process_budget(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    budget = message.text.split()[0]
    database.set_user_info(user_id, budget=budget)
    await state.set_state(ProfileStates.waiting_height)
    await message.answer("Твой рост (в см)? Напиши число или пропусти.", reply_markup=ReplyKeyboardRemove())

@dp.message(ProfileStates.waiting_budget, F.text == "⏩ Пропустить")
async def skip_budget(message: Message, state: FSMContext):
    await state.set_state(ProfileStates.waiting_height)
    await message.answer("Твой рост (в см)? Напиши число или пропусти.", reply_markup=ReplyKeyboardRemove())

@dp.message(ProfileStates.waiting_height, F.text)
async def process_height(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    text = message.text.strip()
    if text.isdigit():
        database.set_user_info(user_id, height=int(text))
    await state.set_state(ProfileStates.waiting_age)
    await message.answer("Твой возраст? Напиши число или пропусти.")

@dp.message(ProfileStates.waiting_height, F.text == "⏩ Пропустить")
async def skip_height(message: Message, state: FSMContext):
    await state.set_state(ProfileStates.waiting_age)
    await message.answer("Твой возраст? Напиши число или пропусти.")

@dp.message(ProfileStates.waiting_age, F.text)
async def process_age(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    text = message.text.strip()
    if text.isdigit():
        database.set_user_info(user_id, age=int(text))
    await state.set_state(ProfileStates.waiting_size)
    await message.answer("Твой размер одежды (например, S, M, L, 42, 46)? Напиши или пропусти.")

@dp.message(ProfileStates.waiting_age, F.text == "⏩ Пропустить")
async def skip_age(message: Message, state: FSMContext):
    await state.set_state(ProfileStates.waiting_size)
    await message.answer("Твой размер одежды? Напиши или пропусти.")

@dp.message(ProfileStates.waiting_size, F.text)
async def process_size(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    size = message.text.strip()
    if size != "⏩ Пропустить":
        database.set_user_info(user_id, clothing_size=size)
    await state.clear()
    await message.answer(
        "🎉 Анкета заполнена! Теперь я знаю о тебе больше и смогу давать более точные советы.\n\n"
        "Отправляй фото или задавай вопросы!",
        reply_markup=get_main_keyboard()
    )

@dp.message(ProfileStates.waiting_size, F.text == "⏩ Пропустить")
async def skip_size(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Хорошо! Анкета завершена. Отправляй фото или задавай вопросы.",
        reply_markup=get_main_keyboard()
    )

# ---- Профиль (отображаем все данные) ----
@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    user_id = str(message.from_user.id)
    user = database.get_user(user_id)
    used_free = user.get("total_free_requests", 0)
    bonus = user.get("bonus_requests", 0)
    paid = user.get("paid_requests", 0)
    remaining_free = max(0, 3 - used_free)
    total_remaining = remaining_free + bonus + paid
    text = (
        f"👤 <b>Твой профиль</b>\n\n"
        f"• Пол: {user.get('gender', 'не указан')}\n"
        f"• Стиль: {user.get('style_preference', 'не указан')}\n"
        f"• Тип фигуры: {user.get('figure_type', 'не указан')}\n"
        f"• Цветотип: {user.get('color_type', 'не указан')}\n"
        f"• Бюджет: {user.get('budget', 'не указан')}\n"
        f"• Рост: {user.get('height', 'не указан')} см\n"
        f"• Возраст: {user.get('age', 'не указан')}\n"
        f"• Размер: {user.get('clothing_size', 'не указан')}\n\n"
        f"📊 Бесплатных анализов осталось: {remaining_free} (из 3)\n"
        f"🎁 Бонусных анализов: {bonus}\n"
        f"💰 Купленных анализов: {paid}\n"
        f"• <b>Всего доступно анализов: {total_remaining}</b>\n\n"
        f"Пополнить баланс анализов можно Telegram Stars."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать анкету", callback_data="edit_anketa")],
        [InlineKeyboardButton(text="🔗 Реферальная ссылка", callback_data="show_referral")],
        [InlineKeyboardButton(text="⭐ 1 анализ — 25 Stars", callback_data="buy_1")],
        [InlineKeyboardButton(text="⭐ 3 анализа — 60 Stars", callback_data="buy_3")],
        [InlineKeyboardButton(text="⭐ 5 анализов — 90 Stars", callback_data="buy_5")]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

# ---- Редактирование анкеты (вызов начала опроса с текущими значениями) ----
@dp.callback_query(lambda c: c.data == "edit_anketa")
async def edit_anketa_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ProfileStates.waiting_gender)
    await callback.message.answer(
        "Давай заполним анкету заново. Ты можешь пропустить любой вопрос.\n"
        "👇 <b>Ты парень или девушка?</b>",
        parse_mode="HTML",
        reply_markup=get_gender_keyboard()
    )
    await callback.answer()
    await callback.message.delete()

# ---- Остальной код (обработчики фото, текста, платежей) остаётся без изменений, но нужно добавить передачу новых параметров в GigaChat ----
# В функции handle_photo перед вызовом gemini.analyze_style добавим сбор всех параметров пользователя:

# user = database.get_user(user_id)
# gender = user.get("gender", "")
# style = user.get("style_preference", "")
# figure = user.get("figure_type", "")
# color = user.get("color_type", "")
# budget = user.get("budget", "")
# height = user.get("height", "")
# age = user.get("age", "")
# size = user.get("clothing_size", "")

# personal_prompt = SYSTEM_PROMPT
# if gender: personal_prompt += f"\nПол: {gender}."
# if style: personal_prompt += f"\nПредпочитаемый стиль: {style}."
# if figure: personal_prompt += f"\nТип фигуры: {figure}."
# if color: personal_prompt += f"\nЦветотип: {color}."
# if budget: personal_prompt += f"\nБюджет: {budget}."
# if height: personal_prompt += f"\nРост: {height} см."
# if age: personal_prompt += f"\nВозраст: {age}."
# if size: personal_prompt += f"\nРазмер одежды: {size}."

# --- (дальше без изменений) ---

# ВНИМАНИЕ: В коде выше опущены обработчики фото, текста, платежей и другие из-за ограничения длины.
# Я предоставлю полный файл bot.py отдельно, если вы готовы его заменить.
