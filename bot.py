import asyncio
import logging
import aiohttp
import json
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.filters import Command, CommandStart, CommandObject
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
    GIGACHAT_SECRET,
    YOOKASSA_PROVIDER_TOKEN
)

from gigachat_client import GigaChatClientWrapper
from prompts import SYSTEM_PROMPT
from affiliate import generate_affiliate_links
import database
import image_utils
from cache import last_results_cache
from states import ProfileStates  # импортируем состояния

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
        [KeyboardButton(text="💎 Премиум"), KeyboardButton(text="🔗 Рефералка")],
        [KeyboardButton(text="💬 Спросить стилиста"), KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_result_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🔄 Ещё совет", callback_data="more_advice")],
        [InlineKeyboardButton(text="📤 Поделиться", callback_data="share_result")],
        [InlineKeyboardButton(text="⭐ В избранное", callback_data="save_favorite")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---- Вспомогательная функция начисления бонуса ----
async def grant_welcome_bonus(user_id: str):
    """Начисляет бонус +1 запрос, если пользователь ещё не получал его."""
    user = database.get_user(user_id)
    if not user.get("welcome_bonus_granted", False):
        # Начисляем бонус
        new_bonus = user.get("bonus_requests", 0) + 1
        database.update_user(user_id, {
            "bonus_requests": new_bonus,
            "welcome_bonus_granted": True
        })
        logger.info(f"Welcome bonus granted to user {user_id}")

# ---- Обработчики команд ----
@dp.message(CommandStart(deep_link=True))
async def cmd_start_with_ref(message: Message, command: CommandObject, state: FSMContext):
    user_id = str(message.from_user.id)
    if command.args:
        ref_code = command.args
        database.apply_referral(user_id, ref_code)
    await cmd_start(message, state)

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    logger.info(f"Start command from user {user_id}")
    # Очищаем кэш для этого пользователя, если есть
    if user_id in last_results_cache:
        del last_results_cache[user_id]
    try:
        user = database.get_user(user_id)
        # Проверяем, заполнен ли профиль
        if not user.get("gender") or not user.get("style_preference"):
            # Переходим в состояние выбора пола
            await state.set_state(ProfileStates.waiting_gender)
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
                "с учётом трендов 2026.\n\n"
                "Также можешь задать текстовый вопрос о моде — я помогу!\n\n"
                "📸 <b>Жду фото или вопрос!</b>",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
    except Exception as e:
        logger.exception(f"Error in start handler: {e}")
        await message.answer("❌ Произошла внутренняя ошибка. Попробуй позже.")

# ---- Обработчики FSM (опрос) ----
@dp.message(ProfileStates.waiting_gender, F.text.in_(["👩 Девушка", "👨 Парень"]))
async def process_gender(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    gender = message.text.split()[1]  # "Девушка" или "Парень"
    database.set_user_info(user_id, gender=gender)
    # Переходим к выбору стиля
    await state.set_state(ProfileStates.waiting_style)
    await message.answer(
        "Отлично! А какой стиль тебе ближе?",
        reply_markup=get_style_keyboard()
    )

@dp.message(ProfileStates.waiting_gender, F.text == "⏩ Пропустить")
async def skip_gender(message: Message, state: FSMContext):
    await state.set_state(ProfileStates.waiting_style)
    await message.answer(
        "Хорошо, пропустим этот вопрос. А какой стиль тебе ближе?",
        reply_markup=get_style_keyboard()
    )

@dp.message(ProfileStates.waiting_style, F.text.in_(["👕 Повседневный", "💼 Деловой", "🌸 Романтичный", "⚽ Спортивный"]))
async def process_style(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    style = message.text.split()[1]  # "Повседневный" и т.д.
    database.set_user_info(user_id, style=style)
    # Начисляем приветственный бонус
    await grant_welcome_bonus(user_id)
    # Завершаем FSM
    await state.clear()
    await message.answer(
        "Спасибо! Теперь отправь мне фото, и я проанализирую образ.\n\n"
        "Также ты можешь просто задать текстовый вопрос – я помогу!\n\n"
        "🎁 <b>В подарок ты получил +1 бесплатный анализ!</b>",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

@dp.message(ProfileStates.waiting_style, F.text == "⏩ Пропустить")
async def skip_style(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    # Начисляем бонус даже если стиль не выбран
    await grant_welcome_bonus(user_id)
    await state.clear()
    await message.answer(
        "Хорошо, если захочешь заполнить позже — просто нажми /profile.\n\n"
        "А пока отправь фото или задай вопрос!\n\n"
        "🎁 <b>В подарок ты получил +1 бесплатный анализ!</b>",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

# ---- Обработчик для любых других сообщений во время опроса ----
@dp.message(ProfileStates.waiting_gender)
async def invalid_gender_input(message: Message):
    await message.answer(
        "Пожалуйста, выбери свой пол с помощью кнопок ниже 👇",
        reply_markup=get_gender_keyboard()
    )

@dp.message(ProfileStates.waiting_style)
async def invalid_style_input(message: Message):
    await message.answer(
        "Пожалуйста, выбери предпочитаемый стиль с помощью кнопок ниже 👇",
        reply_markup=get_style_keyboard()
    )

# ---- Остальные обработчики (команды, фото, текст и т.д.) остаются без изменений ----
# ... (здесь вставляем весь остальной код из предыдущей версии bot.py, начиная с команд profile, premium, referral и т.д.)
# ВНИМАНИЕ: Ниже нужно вставить весь код, который был после этого места. 
# Чтобы не дублировать, я приведу оставшуюся часть ниже, но вы должны скопировать её из предыдущего bot.py и вставить сюда.

# ---- Обработчики команд (profile, premium, referral, help, favorites) ----
@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    user_id = str(message.from_user.id)
    user = database.get_user(user_id)
    free = max(0, 3 - user.get("total_free_requests", 0)) + user.get("bonus_requests", 0)
    text = (
        f"👤 <b>Твой профиль</b>\n\n"
        f"• Пол: {user.get('gender', 'не указан')}\n"
        f"• Стиль: {user.get('style_preference', 'не указан')}\n"
        f"• 📊 Бесплатных анализов осталось: {free}\n"
        f"• 💎 Премиум: {'активна' if database.is_premium(user_id) else 'нет'}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_profile")],
        [InlineKeyboardButton(text="🔗 Моя реферальная ссылка", callback_data="show_referral")]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@dp.message(Command("premium"))
async def cmd_premium(message: Message):
    user_id = str(message.from_user.id)
    if database.is_premium(user_id):
        await message.answer(
            "✅ У вас активна премиум-подписка! Все запросы безлимитны.",
            reply_markup=get_main_keyboard()
        )
    else:
        used = database.get_user(user_id).get("total_free_requests", 0)
        bonus = database.get_user(user_id).get("bonus_requests", 0)
        remaining = max(0, 3 - used) + bonus
        await message.answer(
            f"🔓 У вас осталось <b>{remaining}</b> бесплатных анализов (3 базовых + бонусы).\n\n"
            "💎 <b>Премиум-подписка</b> — 299₽/мес, безлимит\n\n"
            "Нажмите кнопку «Премиум» в главном меню, чтобы оплатить.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )

@dp.message(Command("referral"))
async def cmd_referral(message: Message):
    user_id = str(message.from_user.id)
    link = database.get_referral_link(user_id)
    user = database.get_user(user_id)
    bonus = user.get("bonus_requests", 0)
    await message.answer(
        f"🔗 <b>Твоя реферальная ссылка</b>\n\n"
        f"{link}\n\n"
        f"📢 <b>Как это работает</b>\n"
        f"• Твой друг переходит по ссылке и начинает пользоваться ботом\n"
        f"• Вы оба получаете <b>+1 бесплатный анализ</b>!\n"
        f"• Сейчас у тебя <b>{bonus}</b> бонусных анализов.\n\n"
        f"Приглашай друзей — получай больше бесплатных анализов!",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "💡 <b>Как пользоваться ботом</b>\n\n"
        "1️⃣ Отправь фото в полный рост – получи анализ образа\n"
        "2️⃣ Напиши вопрос стилисту – получи текстовую консультацию\n"
        "3️⃣ Сохраняй понравившиеся идеи в избранное\n"
        "4️⃣ Оплати подписку, чтобы снять лимиты\n"
        "5️⃣ Приглашай друзей по реферальной ссылке – получай бонусные анализы\n\n"
        "<b>Команды:</b>\n"
        "/start — начать заново\n"
        "/profile — мой профиль\n"
        "/premium — информация о подписке\n"
        "/referral — реферальная ссылка\n"
        "/favorites — показать сохранённые образы\n"
        "/help — эта справка\n\n"
        "🔜 <b>Скоро в боте:</b>\n"
        "• Интеграция с магазинами\n"
        "• Виртуальная примерка\n"
        "• Личный гардероб\n"
        "• Сборка образов по фото",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

@dp.message(Command("favorites"))
async def cmd_favorites(message: Message):
    user_id = str(message.from_user.id)
    favorites = database.get_favorites(user_id)
    if not favorites:
        await message.answer(
            "⭐ У тебя пока нет сохранённых образов.",
            reply_markup=get_main_keyboard()
        )
        return
    text = "⭐ <b>Сохранённые образы:</b>\n\n"
    for idx, fav in enumerate(favorites[:10], 1):
        text += f"{idx}. {fav['result_text'][:100]}...\n"
    await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())

# ---- Обработчики кнопок главного меню (без изменений) ----
@dp.message(F.text == "📸 Анализировать")
async def main_analyze(message: Message):
    await message.answer(
        "📸 Отправь мне фото в полный рост, и я оценю твой образ!",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(F.text == "👤 Мой профиль")
async def main_profile(message: Message):
    await cmd_profile(message)

@dp.message(F.text == "💎 Премиум")
async def handle_premium_button(message: Message):
    price_rub = 299
    price_kopecks = price_rub * 100
    provider_data = {
        "receipt": {
            "items": [
                {
                    "description": "Премиум-подписка на 1 месяц (безлимитный доступ)",
                    "quantity": "1.00",
                    "amount": {
                        "value": f"{price_rub:.2f}",
                        "currency": "RUB"
                    },
                    "vat_code": 1
                }
            ]
        }
    }
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="Премиум-подписка",
        description="Безлимитный доступ к анализу стиля на 1 месяц",
        payload="premium_30d",
        provider_token=YOOKASSA_PROVIDER_TOKEN,
        currency="RUB",
        prices=[LabeledPrice(label="1 месяц", amount=price_kopecks)],
        need_email=True,
        send_email_to_provider=True,
        provider_data=json.dumps(provider_data)
    )

@dp.message(F.text == "🔗 Рефералка")
async def main_referral(message: Message):
    await cmd_referral(message)

@dp.message(F.text == "💬 Спросить стилиста")
async def ask_stylist(message: Message):
    await message.answer(
        "💬 <b>Спросите стилиста</b>\n\n"
        "Напишите свой вопрос о моде, стиле, сочетании цветов или подборе одежды.\n"
        "Я отвечу текстом. Например:\n"
        "• «Что надеть на свидание?»\n"
        "• «Какие цвета сочетаются с зелёным?»\n"
        "• «Как выбрать джинсы?»",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(F.text == "❓ Помощь")
async def main_help(message: Message):
    await cmd_help(message)

# ---- Обработчик фото ----
@dp.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    logger.info(f"Photo handler called for user {user_id}")

    # Если пользователь находится в состоянии опроса, прерываем FSM
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await message.answer("Ок, продолжим с анализа фото. Но сначала заполни свой профиль позже через /profile.")

    photo = message.photo[-1]
    if photo.file_size > 5 * 1024 * 1024:
        await message.reply("⚠️ Фото слишком большое (более 5 МБ). Пожалуйста, отправьте изображение поменьше.")
        return

    if user_id != DEVELOPER_ID:
        if not database.can_request(user_id):
            await message.reply(
                "❌ <b>Лимит бесплатных запросов исчерпан</b>\n\n"
                "Вы использовали все бесплатные анализы.\n"
                "Чтобы продолжить, оформите премиум-подписку или пригласите друга по реферальной ссылке.\n\n"
                "💎 <b>Премиум-подписка</b> — 299₽/мес, безлимит\n"
                "🔗 <b>Реферальная ссылка</b> — в меню «Профиль» или команда /referral",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
            return

    file = await bot.get_file(photo.file_id)
    file_path = file.file_path
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"

    await message.reply("🔍 Анализирую ваш образ... Это займёт несколько секунд.", reply_markup=ReplyKeyboardRemove())

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

        last_results_cache[user_id] = result_with_links

        await message.reply(
            result_with_links,
            reply_markup=get_result_keyboard(),
            parse_mode="HTML"
        )

        if user_id != DEVELOPER_ID and not database.is_premium(user_id):
            database.use_request(user_id)

    except Exception as e:
        logger.exception("Ошибка обработки фото: %s", e)
        await message.reply(
            "❌ Не удалось проанализировать фото. Пожалуйста, отправьте другое, более чёткое изображение в полный рост.",
            reply_markup=get_main_keyboard()
        )

# ---- Обработчик текстовых вопросов ----
@dp.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    if message.text.startswith('/'):
        return
    if message.text in ["📸 Анализировать", "👤 Мой профиль", "💎 Премиум", "🔗 Рефералка", "💬 Спросить стилиста", "❓ Помощь"]:
        return

    # Если пользователь в процессе опроса, игнорируем текстовые запросы
    current_state = await state.get_state()
    if current_state is not None:
        await message.answer("Пожалуйста, сначала завершите настройку профиля с помощью кнопок.")
        return

    user_id = str(message.from_user.id)
    if user_id != DEVELOPER_ID:
        if not database.can_request(user_id):
            await message.reply(
                "❌ <b>Лимит бесплатных запросов исчерпан</b>\n\n"
                "Вы использовали все бесплатные анализы.\n"
                "Оформите премиум-подписку или пригласите друга по реферальной ссылке.\n\n"
                "💎 <b>Премиум-подписка</b> — 299₽/мес, безлимит\n"
                "🔗 <b>Реферальная ссылка</b> — в меню «Профиль» или команда /referral",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
            return

    await message.reply("💭 Думаю... Это займёт несколько секунд.", reply_markup=ReplyKeyboardRemove())

    try:
        user = database.get_user(user_id)
        gender = user.get("gender", "")
        style = user.get("style_preference", "")
        text_prompt = (
            "Ты — профессиональный стилист-мужчина. Отвечай дружелюбно, но сдержанно, как эксперт. "
            "Говори **только на русском языке**, используй мужской род о себе. "
            "Избегай иностранных слов и сложных терминов, говори просто и понятно. "
            "Обращайся к клиенту на «ты». Учитывай реалии 2026 года и российский контекст (бренды с WB/Ozon).\n\n"
            f"Пользователь: {gender if gender else 'не указан'}, стиль: {style if style else 'не указан'}."
        )
        answer = await gemini.generate_text(message.text, system_prompt=text_prompt)
        await message.reply(answer, parse_mode="HTML", reply_markup=get_main_keyboard())

        if user_id != DEVELOPER_ID and not database.is_premium(user_id):
            database.use_request(user_id)

    except Exception as e:
        logger.exception("Ошибка текстового запроса: %s", e)
        await message.reply(
            "❌ Не удалось обработать запрос. Попробуйте позже.",
            reply_markup=get_main_keyboard()
        )

# ---- Обработчики inline-кнопок (редактирование профиля) ----
@dp.callback_query(lambda c: c.data == "edit_profile")
async def edit_profile_menu(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👩/👨 Пол", callback_data="edit_gender")],
        [InlineKeyboardButton(text="👕 Стиль", callback_data="edit_style")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
    ])
    await callback.message.edit_text(
        "🔧 <b>Что хотите изменить?</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_profile")
async def back_to_profile(callback: CallbackQuery):
    await cmd_profile(callback.message)
    await callback.message.delete()
    await callback.answer()

@dp.callback_query(lambda c: c.data == "edit_gender")
async def edit_gender(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👩 Девушка", callback_data="set_gender_Девушка")],
        [InlineKeyboardButton(text="👨 Парень", callback_data="set_gender_Парень")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="edit_profile")]
    ])
    await callback.message.edit_text(
        "Выберите пол:",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("set_gender_"))
async def set_gender_callback(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    gender = callback.data.split("_")[2]
    database.set_user_info(user_id, gender=gender)
    await callback.answer(f"Пол изменён на {gender}!")
    await cmd_profile(callback.message)
    await callback.message.delete()

@dp.callback_query(lambda c: c.data == "edit_style")
async def edit_style(callback: CallbackQuery):
    styles = ["Повседневный", "Деловой", "Романтичный", "Спортивный"]
    buttons = [[InlineKeyboardButton(text=style, callback_data=f"set_style_{style}")] for style in styles]
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="edit_profile")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "Выберите предпочитаемый стиль:",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("set_style_"))
async def set_style_callback(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    style = callback.data.split("_")[2]
    database.set_user_info(user_id, style=style)
    await callback.answer(f"Стиль изменён на {style}!")
    await cmd_profile(callback.message)
    await callback.message.delete()

@dp.callback_query(lambda c: c.data == "show_referral")
async def show_referral_callback(callback: CallbackQuery):
    await cmd_referral(callback.message)
    await callback.answer()
    await callback.message.delete()

# ---- Обработчики inline-кнопок (для результата анализа) ----
@dp.callback_query(lambda c: c.data == "more_advice")
async def more_advice_callback(callback: CallbackQuery):
    await callback.answer("Советую отправить новое фото для анализа!", show_alert=False)
    await callback.message.answer("📸 Отправь мне другое фото, и я снова проанализирую твой образ.")
    await callback.message.delete()

@dp.callback_query(lambda c: c.data == "share_result")
async def share_result_callback(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    result = last_results_cache.get(user_id)
    if not result:
        await callback.answer("Не найден результат анализа. Отправьте новое фото.", show_alert=True)
        return
    try:
        img_bytes = image_utils.create_result_image(result)
        await callback.message.answer_photo(
            photo=img_bytes,
            caption="✨ Твой результат в виде картинки для публикации! ✨"
        )
        await callback.answer("Картинка готова!", show_alert=False)
    except Exception as e:
        logger.exception("Ошибка генерации картинки")
        await callback.answer("Не удалось создать картинку. Попробуйте позже.", show_alert=True)
    await callback.message.delete()

@dp.callback_query(lambda c: c.data == "save_favorite")
async def save_favorite_callback(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    result = last_results_cache.get(user_id)
    if not result:
        await callback.answer("Не найден результат анализа. Отправьте новое фото.", show_alert=True)
        return
    database.add_favorite(user_id, result)
    await callback.answer("Результат сохранён в избранное!", show_alert=False)
    await callback.message.delete()

# ---- Обработчики платежей ----
@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def process_payment(message: Message):
    user_id = str(message.from_user.id)
    payload = message.successful_payment.invoice_payload

    if payload == "premium_30d":
        database.set_premium(user_id, duration_days=30)
        await message.answer(
            "✅ <b>Подписка активирована!</b>\n"
            "Теперь вы можете анализировать образы без ограничений.\n"
            "Спасибо за покупку! 🌟",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(
            "Неизвестный тип оплаты. Обратитесь к разработчику.",
            reply_markup=get_main_keyboard()
        )

# ---- Запуск ----
async def main():
    logger.info("Main function started")
    logger.info("Bot starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
