import asyncio
import logging
import aiohttp
import json
from datetime import datetime, timezone, timedelta
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
    YOOKASSA_PROVIDER_TOKEN,
    REPLICATE_API_TOKEN
)

from gigachat_client import GigaChatClientWrapper
from prompts import SYSTEM_PROMPT
from affiliate import generate_affiliate_links
import database
import image_utils
import clothing_recognition
from cache import last_results_cache
from states import ProfileStates, WardrobeStates, TryOnStates
from virtual_tryon import VirtualTryOn

logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), "INFO"))
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

gemini = GigaChatClientWrapper(
    client_id=GIGACHAT_CLIENT_ID,
    client_secret=GIGACHAT_SECRET
)

tryon = VirtualTryOn() if REPLICATE_API_TOKEN else None

# ---- Клавиатуры (без изменений) ----
def get_gender_keyboard():
    kb = [[KeyboardButton(text="👩 Девушка"), KeyboardButton(text="👨 Парень")],[KeyboardButton(text="⏩ Пропустить")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_style_keyboard():
    kb = [[KeyboardButton(text="👕 Повседневный"), KeyboardButton(text="💼 Деловой")],[KeyboardButton(text="🌸 Романтичный"), KeyboardButton(text="⚽ Спортивный")],[KeyboardButton(text="⏩ Пропустить")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

def get_main_keyboard():
    kb = [
        [KeyboardButton(text="📸 Анализировать"), KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="💎 Премиум"), KeyboardButton(text="🔗 Рефералка")],
        [KeyboardButton(text="💬 Спросить стилиста"), KeyboardButton(text="🧥 Гардероб")],
        [KeyboardButton(text="👗 Виртуальная примерка"), KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_result_keyboard():
    buttons = [[InlineKeyboardButton(text="🔄 Ещё совет", callback_data="more_advice")],[InlineKeyboardButton(text="📤 Поделиться", callback_data="share_result")],[InlineKeyboardButton(text="⭐ В избранное", callback_data="save_favorite")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_wardrobe_keyboard(items):
    buttons = []
    for item in items:
        clothing_type = item.get('clothing_type', 'неизвестно')
        description = item.get('description', 'без описания')
        short_desc = description[:30] + "..." if len(description) > 30 else description
        text = f"❌ {clothing_type}: {short_desc}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"wardrobe_del_{item['id']}")])
    buttons.append([InlineKeyboardButton(text="➕ Добавить вещь", callback_data="wardrobe_add")])
    buttons.append([InlineKeyboardButton(text="👕 Подобрать образ из гардероба", callback_data="wardrobe_suggest")])
    buttons.append([InlineKeyboardButton(text="🔙 Закрыть", callback_data="wardrobe_close")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_tryon_clothing_keyboard(items, callback_prefix="tryon_cloth"):
    buttons = []
    for item in items:
        clothing_type = item.get('clothing_type', 'неизвестно')
        description = item.get('description', 'без описания')
        short_desc = description[:25] + "..." if len(description) > 25 else description
        text = f"👕 {clothing_type}: {short_desc}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"{callback_prefix}_{item['id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="tryon_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---- Проверка на безопасность ----
async def check_image_safety(image_bytes: bytes) -> bool:
    """
    Проверяет, содержит ли изображение NSFW-контент.
    Возвращает True, если безопасно, False если небезопасно.
    """
    moderation_prompt = (
        "Ты — модератор. Определи, есть ли на фото обнажённые участки тела, "
        "нижнее бельё, купальники, сексуальные позы или интимные сцены. "
        "Ответь только одним словом: 'опасно' или 'безопасно'."
    )
    try:
        result = await gemini.analyze_style(image_bytes, moderation_prompt)
        result_lower = result.strip().lower()
        if 'опасно' in result_lower:
            logger.info("NSFW content detected")
            return False
        else:
            return True
    except Exception as e:
        logger.error(f"Safety check failed: {e}")
        # В случае ошибки лучше пропустить анализ, чтобы не блокировать пользователя
        return True

# ---- Ежедневные бонусы ----
async def add_daily_bonus(user_id: str):
    """Начисляет 0.5 бонуса за каждый день, максимум 3"""
    user = database.get_user(user_id)
    last_bonus_date = user.get("last_bonus_date")
    today = datetime.now(timezone.utc).date().isoformat()
    if last_bonus_date != today:
        current_bonus = user.get("bonus_requests", 0.0)
        new_bonus = min(current_bonus + 0.5, 3.0)  # максимум 3
        database.update_user(user_id, {
            "bonus_requests": new_bonus,
            "last_bonus_date": today
        })
        logger.info(f"Daily bonus added for {user_id}: +0.5 -> {new_bonus}")
        return True, new_bonus
    return False, user.get("bonus_requests", 0.0)

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
    if user_id in last_results_cache:
        del last_results_cache[user_id]
    try:
        user = database.get_user(user_id)
        # Ежедневный бонус
        bonus_added, new_bonus = await add_daily_bonus(user_id)
        bonus_text = f"\n🎁 <b>+0.5 бонусного анализа за сегодня!</b> (всего {int(new_bonus)})\n" if bonus_added else ""

        if not user.get("gender") or not user.get("style_preference"):
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
                f"✨ <b>Снова рад тебя видеть!</b>{bonus_text}\n\n"
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
    gender = message.text.split()[1]
    database.set_user_info(user_id, gender=gender)
    await state.set_state(ProfileStates.waiting_style)
    await message.answer("Отлично! А какой стиль тебе ближе?", reply_markup=get_style_keyboard())

@dp.message(ProfileStates.waiting_gender, F.text == "⏩ Пропустить")
async def skip_gender(message: Message, state: FSMContext):
    await state.set_state(ProfileStates.waiting_style)
    await message.answer("Хорошо, пропустим этот вопрос. А какой стиль тебе ближе?", reply_markup=get_style_keyboard())

@dp.message(ProfileStates.waiting_style, F.text.in_(["👕 Повседневный", "💼 Деловой", "🌸 Романтичный", "⚽ Спортивный"]))
async def process_style(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    style = message.text.split()[1]
    database.set_user_info(user_id, style=style)
    user = database.get_user(user_id)
    if not user.get("welcome_bonus_granted", False):
        new_bonus = user.get("bonus_requests", 0) + 1
        database.update_user(user_id, {"bonus_requests": new_bonus, "welcome_bonus_granted": True})
        await message.answer("🎁 В подарок вы получили +1 бесплатный анализ!")
    await state.clear()
    await message.answer(
        "Спасибо! Теперь отправь мне фото, и я проанализирую образ.\n\n"
        "Также ты можешь просто задать текстовый вопрос – я помогу!",
        reply_markup=get_main_keyboard()
    )

@dp.message(ProfileStates.waiting_style, F.text == "⏩ Пропустить")
async def skip_style(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    user = database.get_user(user_id)
    if not user.get("welcome_bonus_granted", False):
        new_bonus = user.get("bonus_requests", 0) + 1
        database.update_user(user_id, {"bonus_requests": new_bonus, "welcome_bonus_granted": True})
        await message.answer("🎁 В подарок вы получили +1 бесплатный анализ!")
    await state.clear()
    await message.answer(
        "Хорошо, если захочешь заполнить позже — просто нажми /profile.\n\n"
        "А пока отправь фото или задай вопрос!",
        reply_markup=get_main_keyboard()
    )

@dp.message(ProfileStates.waiting_gender)
async def invalid_gender_input(message: Message):
    await message.answer("Пожалуйста, выбери свой пол с помощью кнопок ниже 👇", reply_markup=get_gender_keyboard())

@dp.message(ProfileStates.waiting_style)
async def invalid_style_input(message: Message):
    await message.answer("Пожалуйста, выбери предпочитаемый стиль с помощью кнопок ниже 👇", reply_markup=get_style_keyboard())

# ---- Обработчики команд (profile, premium, referral, help, favorites) ----
@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    user_id = str(message.from_user.id)
    user = database.get_user(user_id)
    free = max(0, 3 - user.get("total_free_requests", 0)) + int(user.get("bonus_requests", 0))
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
        await message.answer("✅ У вас активна премиум-подписка! Все запросы безлимитны.", reply_markup=get_main_keyboard())
    else:
        used = database.get_user(user_id).get("total_free_requests", 0)
        bonus = int(database.get_user(user_id).get("bonus_requests", 0))
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
    bonus = int(user.get("bonus_requests", 0))
    await message.answer(
        f"🔗 <b>Твоя реферальная ссылка</b>\n\n{link}\n\n"
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
        "5️⃣ Приглашай друзей по реферальной ссылке – получай бонусные анализы\n"
        "6️⃣ Добавляй вещи в гардероб – получай подборки образов\n"
        "7️⃣ Виртуальная примерка – примерь любую вещь из гардероба на своё фото\n\n"
        "<b>Команды:</b>\n"
        "/start — начать заново\n"
        "/profile — мой профиль\n"
        "/premium — информация о подписке\n"
        "/referral — реферальная ссылка\n"
        "/favorites — показать сохранённые образы\n"
        "/wardrobe — мой гардероб\n"
        "/help — эта справка\n\n"
        "🔜 <b>Скоро в боте:</b>\n"
        "• Интеграция с магазинами\n"
        "• Ежедневные бонусы (уже работают!)",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

# ---- Избранное (пагинация) ----
@dp.message(Command("favorites"))
async def cmd_favorites(message: Message):
    user_id = str(message.from_user.id)
    favorites = database.get_favorites(user_id)
    if not favorites:
        await message.answer("⭐ У тебя пока нет сохранённых образов.", reply_markup=get_main_keyboard())
        return
    await show_favorites_page(message, favorites, page=0)

async def show_favorites_page(message: Message, favorites: list, page: int):
    items_per_page = 5
    total_pages = (len(favorites) + items_per_page - 1) // items_per_page
    if page >= total_pages: page = total_pages - 1
    if page < 0: page = 0
    start = page * items_per_page
    end = start + items_per_page
    page_favorites = favorites[start:end]
    text = f"⭐ <b>Сохранённые образы</b> (страница {page+1}/{total_pages if total_pages>0 else 1}):\n\n"
    for idx, fav in enumerate(page_favorites, start=start+1):
        short_text = fav['result_text'][:80] + "..." if len(fav['result_text']) > 80 else fav['result_text']
        text += f"{idx}. {short_text}\n"
    buttons = []
    for fav in page_favorites:
        buttons.append([InlineKeyboardButton(text=f"❌ Удалить запись #{fav['id']}", callback_data=f"delete_fav_{fav['id']}")])
    nav_buttons = []
    if page > 0: nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"fav_page_{page-1}"))
    if page < total_pages - 1: nav_buttons.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"fav_page_{page+1}"))
    if nav_buttons: buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton(text="🔙 Закрыть", callback_data="close_favorites")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    if hasattr(message, 'edit_text'):
        await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@dp.callback_query(lambda c: c.data.startswith("fav_page_"))
async def favorites_page_callback(callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    user_id = str(callback.from_user.id)
    favorites = database.get_favorites(user_id)
    if not favorites:
        await callback.message.edit_text("⭐ У тебя пока нет сохранённых образов.", reply_markup=None)
        await callback.answer()
        return
    await show_favorites_page(callback.message, favorites, page)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("delete_fav_"))
async def delete_favorite_callback(callback: CallbackQuery):
    fav_id = int(callback.data.split("_")[2])
    user_id = str(callback.from_user.id)
    database.delete_favorite(user_id, fav_id)
    favorites = database.get_favorites(user_id)
    if not favorites:
        await callback.message.edit_text("⭐ У тебя пока нет сохранённых образов.", reply_markup=None)
        await callback.answer("Запись удалена!")
        return
    await show_favorites_page(callback.message, favorites, page=0)
    await callback.answer("Запись удалена!")

@dp.callback_query(lambda c: c.data == "close_favorites")
async def close_favorites(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()

# ---- Обработчики кнопок главного меню ----
@dp.message(F.text == "📸 Анализировать")
async def main_analyze(message: Message):
    await message.answer("📸 Отправь мне фото в полный рост, и я оценю твой образ!", reply_markup=ReplyKeyboardRemove())

@dp.message(F.text == "👤 Мой профиль")
async def main_profile(message: Message):
    await cmd_profile(message)

@dp.message(F.text == "💎 Премиум")
async def handle_premium_button(message: Message):
    price_rub = 299
    price_kopecks = price_rub * 100
    provider_data = {"receipt": {"items": [{"description": "Премиум-подписка на 1 месяц (безлимитный доступ)", "quantity": "1.00", "amount": {"value": f"{price_rub:.2f}", "currency": "RUB"}, "vat_code": 1}]}}
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

@dp.message(F.text == "🧥 Гардероб")
async def wardrobe_menu(message: Message):
    user_id = str(message.from_user.id)
    items = database.get_wardrobe(user_id)
    if not items:
        await message.answer(
            "🧥 <b>Твой гардероб пока пуст</b>\n\n"
            "Чтобы добавить вещь, нажми «➕ Добавить вещь» и отправь фото.",
            parse_mode="HTML",
            reply_markup=get_wardrobe_keyboard([])
        )
    else:
        text = "🧥 <b>Твой гардероб:</b>\n\n"
        for item in items:
            clothing_type = item.get('clothing_type', 'неизвестно')
            description = item.get('description', 'без описания')
            text += f"• {clothing_type}: {description}\n"
        await message.answer(text, parse_mode="HTML", reply_markup=get_wardrobe_keyboard(items))

@dp.message(F.text == "👗 Виртуальная примерка")
async def virtual_tryon_start(message: Message, state: FSMContext):
    if not tryon:
        await message.answer("❌ Виртуальная примерка временно недоступна. Попробуйте позже.")
        return
    await state.set_state(TryOnStates.waiting_person_photo)
    await message.answer(
        "📸 <b>Виртуальная примерка</b>\n\n"
        "Отправьте фото человека (в полный рост или хотя бы верхнюю часть), "
        "на которое хотите примерить одежду.\n\n"
        "Фото должно быть чётким, лучше на светлом фоне.",
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove()
    )

@dp.message(F.text == "❓ Помощь")
async def main_help(message: Message):
    await cmd_help(message)

# ---- Обработчики гардероба (исправлены дубли) ----
@dp.callback_query(lambda c: c.data == "wardrobe_add")
async def wardrobe_add_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(WardrobeStates.waiting_for_photo)
    await callback.message.answer(
        "📸 Отправь фото предмета одежды, который хочешь добавить в гардероб.\n"
        "После фото я спрошу тип и описание."
    )
    await callback.answer()
    await callback.message.delete()

@dp.message(WardrobeStates.waiting_for_photo, F.photo)
async def wardrobe_add_photo(message: Message, state: FSMContext):
    user_id = str(message.from_user.id)
    photo = message.photo[-1]
    if photo.file_size > 5 * 1024 * 1024:
        await message.reply("⚠️ Фото слишком большое (до 5 МБ).")
        return
    file = await bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file.file_path}"
    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            if resp.status != 200:
                await message.reply("❌ Не удалось загрузить фото.")
                return
            await resp.read()
    await state.update_data(image_url=file_url)
    await state.set_state(WardrobeStates.waiting_clothing_type)
    await message.answer(
        "📝 <b>Какой тип одежды?</b>\n\n"
        "Напишите одним словом: футболка, рубашка, свитер, джинсы, брюки, платье, куртка и т.д.",
        parse_mode="HTML"
    )

@dp.message(WardrobeStates.waiting_for_photo)
async def wardrobe_add_invalid(message: Message):
    await message.answer("Пожалуйста, отправьте фото одежды.")

@dp.message(WardrobeStates.waiting_clothing_type, F.text)
async def wardrobe_clothing_type(message: Message, state: FSMContext):
    clothing_type = message.text.strip().lower()
    await state.update_data(clothing_type=clothing_type)
    await state.set_state(WardrobeStates.waiting_description)
    await message.answer(
        "📝 <b>Опишите вещь</b> (цвет, материал, особенности):\n\n"
        "Например: «чёрные джинсы скинни», «белая хлопковая рубашка»",
        parse_mode="HTML"
    )

@dp.message(WardrobeStates.waiting_clothing_type)
async def invalid_clothing_type(message: Message):
    await message.answer("Пожалуйста, напишите тип одежды текстом.")

@dp.message(WardrobeStates.waiting_description, F.text)
async def wardrobe_description(message: Message, state: FSMContext):
    description = message.text.strip()
    data = await state.get_data()
    image_url = data.get("image_url")
    clothing_type = data.get("clothing_type")
    user_id = str(message.from_user.id)

    if not image_url or not clothing_type:
        await message.answer("❌ Ошибка, попробуйте снова нажать «➕ Добавить вещь».")
        await state.clear()
        return

    database.add_to_wardrobe(user_id, image_url, clothing_type, description)
    await state.clear()
    await message.answer(
        f"✅ <b>Вещь добавлена в гардероб!</b>\n\n"
        f"Тип: {clothing_type}\nОписание: {description}\n\n"
        f"Можешь добавить ещё или посмотреть гардероб по кнопке «Гардероб».",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

@dp.message(WardrobeStates.waiting_description)
async def invalid_description(message: Message):
    await message.answer("Пожалуйста, напишите описание текстом.")

@dp.callback_query(lambda c: c.data.startswith("wardrobe_del_"))
async def wardrobe_delete_callback(callback: CallbackQuery):
    item_id = int(callback.data.split("_")[2])
    user_id = str(callback.from_user.id)
    database.delete_from_wardrobe(item_id, user_id)
    items = database.get_wardrobe(user_id)
    if not items:
        text = "🧥 <b>Твой гардероб пока пуст</b>\n\nЧтобы добавить вещь, нажми «➕ Добавить вещь»."
    else:
        text = "🧥 <b>Твой гардероб:</b>\n\n"
        for item in items:
            clothing_type = item.get('clothing_type', 'неизвестно')
            description = item.get('description', 'без описания')
            text += f"• {clothing_type}: {description}\n"
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_wardrobe_keyboard(items))
    await callback.answer("Вещь удалена!")

@dp.callback_query(lambda c: c.data == "wardrobe_suggest")
async def wardrobe_suggest_callback(callback: CallbackQuery):
    user_id = str(callback.from_user.id)
    items = database.get_wardrobe(user_id)
    if len(items) < 2:
        await callback.answer("Для подбора образа нужно хотя бы 2 вещи в гардеробе!", show_alert=True)
        return
    wardrobe_text = "\n".join([f"- {item.get('clothing_type', 'неизвестно')}: {item.get('description', 'без описания')}" for item in items])
    prompt = (
        f"Ты — стилист. У пользователя есть следующие вещи:\n{wardrobe_text}\n\n"
        f"Предложи 2-3 варианта комбинаций из этих вещей, которые составят стильный образ. "
        f"Учитывай, что у пользователя пол: {database.get_user(user_id).get('gender', 'не указан')}, "
        f"предпочтения в стиле: {database.get_user(user_id).get('style_preference', 'не указан')}. "
        f"Ответ должен быть на русском, дружелюбным, с конкретными советами."
    )
    await callback.message.answer("🧠 Думаю над образами...")
    try:
        result = await gemini.generate_text(prompt)
        await callback.message.answer(result, parse_mode="HTML")
    except Exception as e:
        logger.exception("Ошибка подбора образа")
        await callback.message.answer("❌ Не удалось подобрать образ. Попробуйте позже.")
    await callback.answer()

@dp.callback_query(lambda c: c.data == "wardrobe_close")
async def wardrobe_close_callback(callback: CallbackQuery):
    await callback.message.delete()
    await callback.answer()

# ---- Обработчики виртуальной примерки ----
@dp.message(TryOnStates.waiting_person_photo, F.photo)
async def tryon_person_photo_received(message: Message, state: FSMContext):
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file.file_path}"
    await state.update_data(person_image_url=file_url)
    user_id = str(message.from_user.id)
    items = database.get_wardrobe(user_id)
    if not items:
        await message.answer(
            "У вас пока нет вещей в гардеробе. Сначала добавьте одежду через кнопку «Гардероб».",
            reply_markup=get_main_keyboard()
        )
        await state.clear()
        return
    await state.set_state(TryOnStates.waiting_clothing_selection)
    await message.answer(
        "Теперь выберите одежду, которую хотите примерить:",
        reply_markup=get_tryon_clothing_keyboard(items)
    )

@dp.message(TryOnStates.waiting_person_photo)
async def tryon_person_photo_invalid(message: Message):
    await message.answer("Пожалуйста, отправьте фото.")

@dp.callback_query(TryOnStates.waiting_clothing_selection, lambda c: c.data.startswith("tryon_cloth_"))
async def tryon_select_clothing(callback: CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split("_")[2])
    user_id = str(callback.from_user.id)
    items = database.get_wardrobe(user_id)
    selected_item = None
    for item in items:
        if item['id'] == item_id:
            selected_item = item
            break
    if not selected_item:
        await callback.answer("Вещь не найдена.", show_alert=True)
        return
    data = await state.get_data()
    person_image_url = data.get("person_image_url")
    if not person_image_url:
        await callback.answer("Ошибка: фото человека не найдено. Попробуйте начать заново.", show_alert=True)
        await state.clear()
        return
    clothing_image_url = selected_item['image_url']
    await callback.message.answer("🔄 Выполняю примерку... Это может занять до 30 секунд.")
    await callback.answer()
    try:
        result_url = await tryon.try_on(person_image_url, clothing_image_url)
        if result_url:
            if isinstance(result_url, list):
                result_url = result_url[0]
            await callback.message.answer_photo(
                photo=result_url,
                caption=f"✨ Примерка '{selected_item['clothing_type']}': {selected_item['description']}"
            )
        else:
            await callback.message.answer("❌ Не удалось выполнить примерку. Попробуйте другое фото или другую вещь.")
    except Exception as e:
        logger.exception("Ошибка примерки")
        await callback.message.answer("❌ Произошла ошибка. Попробуйте позже.")
    await state.clear()

@dp.callback_query(lambda c: c.data == "tryon_cancel")
async def tryon_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Виртуальная примерка отменена.", reply_markup=get_main_keyboard())
    await callback.message.delete()
    await callback.answer()

# ---- Обработчик фото (основной) с проверкой безопасности ----
@dp.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state in [WardrobeStates.waiting_for_photo.state, TryOnStates.waiting_person_photo.state]:
        return
    user_id = str(message.from_user.id)
    logger.info(f"Photo handler called for user {user_id}")
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
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file.file_path}"
    await message.reply("🔍 Анализирую ваш образ... Это займёт несколько секунд.", reply_markup=ReplyKeyboardRemove())
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                if resp.status != 200:
                    await message.reply("❌ Не удалось загрузить фото. Попробуйте ещё раз.")
                    return
                image_bytes = await resp.read()
        
        # ---------- ПРОВЕРКА НА БЕЗОПАСНОСТЬ ----------
        if not await check_image_safety(image_bytes):
            await message.reply(
                "⚠️ <b>Извините, я не могу анализировать фото с откровенным содержанием.</b>\n\n"
                "Пожалуйста, отправьте фото в обычной одежде (футболка, рубашка, платье и т.д.).\n\n"
                "Это необходимо для соблюдения правил и корректной работы стилиста.",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
            return
        # ------------------------------------------------
        
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
    if message.text in ["📸 Анализировать", "👤 Мой профиль", "💎 Премиум", "🔗 Рефералка", "💬 Спросить стилиста", "🧥 Гардероб", "👗 Виртуальная примерка", "❓ Помощь"]:
        return
    current_state = await state.get_state()
    if current_state is not None:
        await message.answer("Пожалуйста, сначала завершите текущее действие с помощью кнопок.")
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
        await message.reply("❌ Не удалось обработать запрос. Попробуйте позже.", reply_markup=get_main_keyboard())

# ---- Обработчики inline-кнопок (редактирование профиля) ----
@dp.callback_query(lambda c: c.data == "edit_profile")
async def edit_profile_menu(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👩/👨 Пол", callback_data="edit_gender")],
        [InlineKeyboardButton(text="👕 Стиль", callback_data="edit_style")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_profile")]
    ])
    await callback.message.edit_text("🔧 <b>Что хотите изменить?</b>", parse_mode="HTML", reply_markup=keyboard)
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
    await callback.message.edit_text("Выберите пол:", reply_markup=keyboard)
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
    await callback.message.edit_text("Выберите предпочитаемый стиль:", reply_markup=keyboard)
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
        await callback.message.answer_photo(photo=img_bytes, caption="✨ Твой результат в виде картинки для публикации! ✨")
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
        await message.answer("Неизвестный тип оплаты. Обратитесь к разработчику.", reply_markup=get_main_keyboard())

# ---- Команда /wardrobe ----
@dp.message(Command("wardrobe"))
async def cmd_wardrobe(message: Message):
    await wardrobe_menu(message)

# ---- Запуск ----
async def main():
    logger.info("Main function started")
    logger.info("Bot starting...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
