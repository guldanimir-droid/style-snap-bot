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
    GIGACHAT_SECRET,
    YOOKASSA_PROVIDER_TOKEN
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

# ---- Проверка на безопасность (смягчённая) ----
async def check_image_safety(image_bytes: bytes) -> bool:
    moderation_prompt = (
        "Ты — модератор. Определи, есть ли на фото обнажённая грудь, половые органы, "
        "явные сексуальные действия или порнография. "
        "Если на фото человек в обычной одежде (футболка, джинсы, платье, куртка и т.п.) — это безопасно. "
        "Ответь только одним словом: 'опасно' или 'безопасно'."
    )
    try:
        result = await gemini.analyze_style(image_bytes, moderation_prompt)
        return 'опасно' not in result.lower()
    except Exception as e:
        logger.error(f"Safety check failed: {e}")
        return True  # в случае ошибки пропускаем

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
            "Отправь своё фото, и я дам совет по стилю.\n"
            "Можешь также задать текстовый вопрос о моде.\n\n"
            "📸 <b>Жду фото или вопрос!</b>",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )

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
    database.set_user_info(user_id, style=style)
    await state.clear()
    await message.answer(
        "Спасибо! Теперь отправь своё фото, и я дам совет.\n"
        "Также можешь задать текстовый вопрос!",
        reply_markup=get_main_keyboard()
    )

@dp.message(ProfileStates.waiting_style, F.text == "⏩ Пропустить")
async def skip_style(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Хорошо! Отправь фото или задай вопрос.",
        reply_markup=get_main_keyboard()
    )

@dp.message(ProfileStates.waiting_gender)
async def invalid_gender_input(message: Message):
    await message.answer("Выбери пол с помощью кнопок 👇", reply_markup=get_gender_keyboard())

@dp.message(ProfileStates.waiting_style)
async def invalid_style_input(message: Message):
    await message.answer("Выбери стиль с помощью кнопок 👇", reply_markup=get_style_keyboard())

# ---- Профиль, рефералка, премиум ----
@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    user_id = str(message.from_user.id)
    user = database.get_user(user_id)
    used = user.get("total_free_requests", 0)
    bonus = user.get("bonus_requests", 0)
    free = max(0, 3 - used) + bonus
    text = (
        f"👤 <b>Твой профиль</b>\n\n"
        f"• Пол: {user.get('gender', 'не указан')}\n"
        f"• Стиль: {user.get('style_preference', 'не указан')}\n"
        f"• 📊 Бесплатных анализов осталось: {free}\n"
        f"• 💎 Премиум: {'активна' if database.is_premium(user_id) else 'нет'}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_profile")],
        [InlineKeyboardButton(text="🔗 Реферальная ссылка", callback_data="show_referral")]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@dp.message(Command("premium"))
async def cmd_premium(message: Message):
    user_id = str(message.from_user.id)
    if database.is_premium(user_id):
        await message.answer("✅ У вас активна премиум-подписка!", reply_markup=get_main_keyboard())
    else:
        used = database.get_user(user_id).get("total_free_requests", 0)
        bonus = database.get_user(user_id).get("bonus_requests", 0)
        remaining = max(0, 3 - used) + bonus
        await message.answer(
            f"🔓 Осталось <b>{remaining}</b> бесплатных анализов.\n\n"
            "💎 <b>Премиум</b> — 299₽/мес, безлимит\n"
            "Нажми «Премиум» в меню, чтобы оплатить.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )

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

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "💡 <b>Как пользоваться</b>\n\n"
        "1️⃣ Отправь фото – получи совет стилиста\n"
        "2️⃣ Напиши вопрос о моде – отвечу текстом\n"
        "3️⃣ Сохраняй советы в избранное\n"
        "4️⃣ Приглашай друзей – получай бонусы\n\n"
        "<b>Команды:</b>\n"
        "/start — начать\n"
        "/profile — мой профиль\n"
        "/premium — подписка\n"
        "/referral — рефералка\n"
        "/favorites — избранное\n"
        "/help — помощь",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

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

@dp.message(F.text == "💎 Премиум")
async def handle_premium_button(message: Message):
    price_rub = 299
    price_kopecks = price_rub * 100
    provider_data = {"receipt": {"items": [{"description": "Премиум-подписка на 1 месяц", "quantity": "1.00", "amount": {"value": f"{price_rub:.2f}", "currency": "RUB"}, "vat_code": 1}]}}
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
        "💬 Напиши свой вопрос о моде, стиле, цветах или одежде.\n"
        "Например: «Что надеть на свидание?» или «Как сочетать зелёный?»",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(F.text == "❓ Помощь")
async def main_help(message: Message):
    await cmd_help(message)

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
    if user_id != DEVELOPER_ID:
        if not database.can_request(user_id):
            await message.reply(
                "❌ Лимит бесплатных анализов исчерпан.\n"
                "Оформи премиум или пригласи друга по реферальной ссылке.",
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
        await message.reply(result_with_links, reply_markup=get_result_keyboard(), parse_mode="HTML")
        if user_id != DEVELOPER_ID and not database.is_premium(user_id):
            database.use_request(user_id)
    except Exception as e:
        logger.exception("Ошибка фото")
        await message.reply("❌ Не удалось проанализировать. Попробуй другое фото.", reply_markup=get_main_keyboard())

# ---- Обработчик текста ----
@dp.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    if message.text.startswith('/'):
        return
    if message.text in ["📸 Анализировать", "👤 Мой профиль", "💎 Премиум", "🔗 Рефералка", "💬 Спросить стилиста", "❓ Помощь"]:
        return
    current_state = await state.get_state()
    if current_state is not None:
        await message.answer("Сначала заверши настройку профиля с помощью кнопок.")
        return
    user_id = str(message.from_user.id)
    if user_id != DEVELOPER_ID:
        if not database.can_request(user_id):
            await message.reply(
                "❌ Лимит бесплатных анализов исчерпан.\n"
                "Оформи премиум или пригласи друга.",
                reply_markup=get_main_keyboard()
            )
            return
    await message.reply("💭 Думаю...", reply_markup=ReplyKeyboardRemove())
    try:
        user = database.get_user(user_id)
        gender = user.get("gender", "")
        style = user.get("style_preference", "")
        text_prompt = (
            "Ты — профессиональный стилист-мужчина. Отвечай дружелюбно, по-русски, используй мужской род. "
            "Обращайся на «ты». Учитывай российский контекст (WB/Ozon).\n\n"
            f"Пользователь: {gender if gender else 'не указан'}, стиль: {style if style else 'не указан'}."
        )
        answer = await gemini.generate_text(message.text, system_prompt=text_prompt)
        await message.reply(answer, parse_mode="HTML", reply_markup=get_main_keyboard())
        if user_id != DEVELOPER_ID and not database.is_premium(user_id):
            database.use_request(user_id)
    except Exception as e:
        logger.exception("Ошибка текста")
        await message.reply("❌ Не удалось обработать. Попробуй позже.", reply_markup=get_main_keyboard())

# ---- Редактирование профиля (inline) ----
@dp.callback_query(lambda c: c.data == "edit_profile")
async def edit_profile_menu(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👩/👨 Пол", callback_data="edit_gender")],
        [InlineKeyboardButton(text="👕 Стиль", callback_data="edit_style")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
    ])
    await callback.message.edit_text("🔧 <b>Что изменить?</b>", parse_mode="HTML", reply_markup=keyboard)
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
    await callback.message.edit_text("Выбери пол:", reply_markup=keyboard)
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
    await callback.message.edit_text("Выбери стиль:", reply_markup=keyboard)
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

# ---- Платежи ----
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
            "✅ Подписка активирована! Теперь безлимит. Спасибо! 🌟",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer("Ошибка оплаты.", reply_markup=get_main_keyboard())

# ---- Запуск ----
async def main():
    logger.info("Bot starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
