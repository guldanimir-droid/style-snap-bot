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

# ---- Редактирование анкеты (вызов начала опроса) ----
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

@dp.callback_query(lambda c: c.data == "show_referral")
async def show_referral_callback(callback: CallbackQuery):
    await cmd_referral(callback.message)
    await callback.answer()
    await callback.message.delete()

# ---- Рефералка ----
@dp.message(Command("referral"))
async def cmd_referral(message: Message):
    user_id = str(message.from_user.id)
    link = database.get_referral_link(user_id)
    bonus = database.get_user(user_id).get("bonus_requests", 0)
    await message.answer(
        f"🔗 <b>Твоя реферальная ссылка</b>\n\n{link}\n\n"
        f"Пригласи друга — вы оба получите <b>+1 анализ</b>!\n"
        f"Сейчас у тебя <b>{bonus}</b> бонусных анализов.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

# ---- Помощь ----
@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "💡 <b>Что умеет этот бот</b>\n\n"
        "✅ Анализировать твои фото и давать советы по стилю\n"
        "✅ Отвечать на текстовые вопросы о моде\n"
        "✅ Сохранять удачные советы в избранное\n"
        "✅ Начислять бонусные анализы за приглашение друзей\n"
        "✅ Продавать дополнительные анализы за Telegram Stars\n"
        "✅ Учитывать твой тип фигуры, цветотип, бюджет, рост, возраст, размер\n\n"
        "<b>Команды:</b>\n"
        "/start — начать\n"
        "/profile — мой профиль\n"
        "/referral — рефералка\n"
        "/favorites — избранное\n"
        "/help — помощь",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

# ---- Избранное (упрощённое) ----
@dp.message(Command("favorites"))
async def cmd_favorites(message: Message):
    user_id = str(message.from_user.id)
    favorites = database.get_favorites(user_id)
    if not favorites:
        await message.answer("⭐ У тебя пока нет сохранённых образов.", reply_markup=get_main_keyboard())
        return
    text = "⭐ <b>Сохранённые образы:</b>\n\n"
    for idx, fav in enumerate(favorites[:20], 1):
        short = fav['result_text'][:80] + "..." if len(fav['result_text']) > 80 else fav['result_text']
        text += f"{idx}. {short}\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"❌ Удалить #{fav['id']}", callback_data=f"del_fav_{fav['id']}")] for fav in favorites[:20]
    ])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Закрыть", callback_data="close_fav")])
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith("del_fav_"))
async def delete_favorite_callback(callback: CallbackQuery):
    fav_id = int(callback.data.split("_")[2])
    user_id = str(callback.from_user.id)
    database.delete_favorite(user_id, fav_id)
    await callback.answer("Удалено!")
    await cmd_favorites(callback.message)
    await callback.message.delete()

@dp.callback_query(lambda c: c.data == "close_fav")
async def close_fav_callback(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()

# ---- Кнопки главного меню ----
@dp.message(F.text == "📸 Анализировать")
async def main_analyze(message: Message):
    await message.answer("📸 Отправь своё фото, и я дам совет по стилю!", reply_markup=ReplyKeyboardRemove())

@dp.message(F.text == "👤 Мой профиль")
async def main_profile(message: Message):
    await cmd_profile(message)

@dp.message(F.text == "🔗 Рефералка")
async def main_referral(message: Message):
    await cmd_referral(message)

@dp.message(F.text == "💬 Спросить стилиста")
async def ask_stylist(message: Message):
    await message.answer(
        "💬 Напиши свой вопрос о моде, стиле, цветах или одежде.\n"
        "Например: «Что надеть на свидание?» или «Как сочетать зелёный?»",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(F.text == "❓ Помощь")
async def main_help(message: Message):
    await cmd_help(message)

# ---- Платежи (пакеты) ----
async def send_package_invoice(chat_id: int, amount: int, stars: int, package_name: str):
    await bot.send_invoice(
        chat_id=chat_id,
        title=package_name,
        description=f"Купить {amount} анализов стиля за {stars} Telegram Stars",
        payload=f"package_{amount}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"{amount} анализов", amount=stars)],
        start_parameter=f"buy_{amount}"
    )

@dp.callback_query(lambda c: c.data == "buy_1")
async def buy_1_analysis(callback: CallbackQuery):
    await send_package_invoice(callback.from_user.id, 1, 25, "1 анализ стиля")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "buy_3")
async def buy_3_analysis(callback: CallbackQuery):
    await send_package_invoice(callback.from_user.id, 3, 60, "3 анализа стиля")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "buy_5")
async def buy_5_analysis(callback: CallbackQuery):
    await send_package_invoice(callback.from_user.id, 5, 90, "5 анализов стиля")
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def process_payment(message: Message):
    user_id = str(message.from_user.id)
    payload = message.successful_payment.invoice_payload
    if payload.startswith("package_"):
        amount = int(payload.split("_")[1])
        for _ in range(amount):
            database.add_paid_analysis(user_id)
        await message.answer(
            f"✅ Оплата прошла успешно! Вам начислено {amount} анализов.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer("Неизвестный тип платежа.", reply_markup=get_main_keyboard())

# ---- Обработчик фото ----
@dp.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
    user_id = str(message.from_user.id)
    photo = message.photo[-1]
    if photo.file_size > 5 * 1024 * 1024:
        await message.reply("⚠️ Фото слишком большое (до 5 МБ).")
        return
    if not database.can_request(user_id):
        await message.reply(
            "❌ У вас закончились бесплатные анализы.\n"
            "Купите пакет анализов в профиле за Telegram Stars.",
            reply_markup=get_main_keyboard()
        )
        return
    file = await bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file.file_path}"
    await message.reply("🔍 Анализирую... пару секунд.", reply_markup=ReplyKeyboardRemove())
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                if resp.status != 200:
                    await message.reply("❌ Не удалось загрузить фото.")
                    return
                image_bytes = await resp.read()
        if not await check_image_safety(image_bytes):
            await message.reply(
                "⚠️ Извините, я не анализирую фото с откровенным содержанием.\n"
                "Отправьте фото в обычной одежде.",
                reply_markup=get_main_keyboard()
            )
            return
        user = database.get_user(user_id)
        # Собираем все параметры для персонализации
        gender = user.get("gender", "")
        style = user.get("style_preference", "")
        figure = user.get("figure_type", "")
        color = user.get("color_type", "")
        budget = user.get("budget", "")
        height = user.get("height", "")
        age = user.get("age", "")
        size = user.get("clothing_size", "")
        personal_prompt = SYSTEM_PROMPT
        if gender:
            personal_prompt += f"\nПол: {gender}."
        if style:
            personal_prompt += f"\nПредпочитаемый стиль: {style}."
        if figure:
            personal_prompt += f"\nТип фигуры: {figure}."
        if color:
            personal_prompt += f"\nЦветотип: {color}."
        if budget:
            personal_prompt += f"\nБюджет: {budget}."
        if height:
            personal_prompt += f"\nРост: {height} см."
        if age:
            personal_prompt += f"\nВозраст: {age}."
        if size:
            personal_prompt += f"\nРазмер одежды: {size}."
        result = await gemini.analyze_style(image_bytes, personal_prompt)
        result_with_links = generate_affiliate_links(result)
        last_results_cache[user_id] = result_with_links
        await message.reply(result_with_links, reply_markup=get_result_keyboard(), parse_mode="HTML")
        database.use_request(user_id)
    except Exception as e:
        logger.exception("Ошибка фото")
        await message.reply("❌ Не удалось проанализировать. Попробуй другое фото.", reply_markup=get_main_keyboard())

# ---- Обработчик текста ----
@dp.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    if message.text.startswith('/'):
        return
    if message.text in ["📸 Анализировать", "👤 Мой профиль", "🔗 Рефералка", "💬 Спросить стилиста", "❓ Помощь"]:
        return
    current_state = await state.get_state()
    if current_state is not None:
        await message.answer("Сначала заверши настройку профиля с помощью кнопок.")
        return
    user_id = str(message.from_user.id)
    if not database.can_request(user_id):
        await message.reply(
            "❌ У вас закончились бесплатные текстовые запросы.\n"
            "Купите анализ или пригласите друга.",
            reply_markup=get_main_keyboard()
        )
        return
    await message.reply("💭 Думаю...", reply_markup=ReplyKeyboardRemove())
    try:
        user = database.get_user(user_id)
        gender = user.get("gender", "")
        style = user.get("style_preference", "")
        figure = user.get("figure_type", "")
        color = user.get("color_type", "")
        budget = user.get("budget", "")
        height = user.get("height", "")
        age = user.get("age", "")
        size = user.get("clothing_size", "")
        text_prompt = (
            "Ты — профессиональный стилист-мужчина. Отвечай дружелюбно, по-русски, используй мужской род. "
            "Обращайся на «ты». Учитывай российский контекст (WB/Ozon).\n\n"
            f"Пользователь: {gender if gender else 'не указан'}, стиль: {style if style else 'не указан'}."
        )
        if figure: text_prompt += f"\nТип фигуры: {figure}."
        if color: text_prompt += f"\nЦветотип: {color}."
        if budget: text_prompt += f"\nБюджет: {budget}."
        if height: text_prompt += f"\nРост: {height} см."
        if age: text_prompt += f"\nВозраст: {age}."
        if size: text_prompt += f"\nРазмер одежды: {size}."
        answer = await gemini.generate_text(message.text, system_prompt=text_prompt)
        await message.reply(answer, parse_mode="HTML", reply_markup=get_main_keyboard())
        database.use_request(user_id)
    except Exception as e:
        logger.exception("Ошибка текста")
        await message.reply("❌ Не удалось обработать. Попробуй позже.", reply_markup=get_main_keyboard())

# ---- Кнопки результата ----
@dp.callback_query(lambda c: c.data == "more_advice")
async def more_advice_callback(callback: CallbackQuery):
    await callback.answer("Отправь новое фото!")
    await callback.message.answer("📸 Отправь другое фото.")
    await callback.message.delete()

@dp.callback_query(lambda c: c.data == "share_result")
async def share_result_callback(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    result = last_results_cache.get(user_id)
    if not result:
        await callback.answer("Нет результата. Отправь фото.")
        return
    try:
        img_bytes = image_utils.create_result_image(result)
        await callback.message.answer_photo(photo=img_bytes, caption="✨ Результат для публикации ✨")
        await callback.answer("Готово!")
    except Exception as e:
        logger.exception("Ошибка генерации картинки")
        await callback.answer("Не удалось создать картинку.")
    await callback.message.delete()

@dp.callback_query(lambda c: c.data == "save_favorite")
async def save_favorite_callback(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    result = last_results_cache.get(user_id)
    if not result:
        await callback.answer("Нет результата.")
        return
    database.add_favorite(user_id, result)
    await callback.answer("Сохранено в избранное!")
    await callback.message.delete()

# ---- Запуск ----
async def main():
    logger.info("Bot starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
