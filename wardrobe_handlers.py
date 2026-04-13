import logging
import random
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

from database import add_wardrobe_item, get_wardrobe_items, delete_wardrobe_item
from supabase_utils import upload_wardrobe_image
from config import TELEGRAM_BOT_TOKEN, GIGACHAT_CLIENT_ID, GIGACHAT_SECRET
from gigachat_client import GigaChatClientWrapper

logger = logging.getLogger(__name__)
router = Router()
bot = Bot(token=TELEGRAM_BOT_TOKEN)
gemini = GigaChatClientWrapper(
    client_id=GIGACHAT_CLIENT_ID,
    client_secret=GIGACHAT_SECRET
)

# Клавиатура главного меню (дублируется, чтобы избежать циклического импорта)
def get_main_keyboard():
    kb = [
        [KeyboardButton(text="📸 Анализировать"), KeyboardButton(text="👤 Мой профиль")],
        [KeyboardButton(text="🔗 Рефералка"), KeyboardButton(text="💬 Спросить стилиста")],
        [KeyboardButton(text="❓ Помощь"), KeyboardButton(text="👕 Виртуальная примерка")],
        [KeyboardButton(text="🔥 Ежедневный совет"), KeyboardButton(text="👗 Мой гардероб")],
        [KeyboardButton(text="🤔 Что надеть?"), KeyboardButton(text="➕ Добавить вещь")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

class AddClothesStates(StatesGroup):
    waiting_photo = State()
    waiting_type = State()
    waiting_description = State()

class TryOnStates(StatesGroup):
    waiting_person_photo = State()

@router.message(Command("add_clothes"))
async def cmd_add_clothes(message: Message, state: FSMContext):
    logger.info(f"Команда /add_clothes от {message.from_user.id}")
    await message.answer("📸 Отправь фотографию вещи, которую хочешь добавить в гардероб.")
    await state.set_state(AddClothesStates.waiting_photo)

@router.message(AddClothesStates.waiting_photo, F.photo)
async def add_clothes_photo(message: Message, state: FSMContext):
    logger.info(f"📸 add_clothes_photo: получили фото от {message.from_user.id}")
    file_id = message.photo[-1].file_id
    await state.update_data(photo_file_id=file_id)
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👕 Футболка"), KeyboardButton(text="👖 Джинсы")],
            [KeyboardButton(text="👗 Платье"), KeyboardButton(text="🧥 Пальто")],
            [KeyboardButton(text="👟 Обувь"), KeyboardButton(text="🎒 Аксессуар")],
            [KeyboardButton(text="Другое"), KeyboardButton(text="⏩ Пропустить")]
        ],
        resize_keyboard=True
    )
    await message.answer("Выбери тип одежды или нажми «Пропустить»:", reply_markup=kb)
    await state.set_state(AddClothesStates.waiting_type)

@router.message(AddClothesStates.waiting_type, F.text)
async def add_clothes_type(message: Message, state: FSMContext):
    logger.info(f"Тип одежды: {message.text}")
    text = message.text
    clothing_type = None if text == "⏩ Пропустить" else text.strip()
    await state.update_data(clothing_type=clothing_type)
    await message.answer("Теперь напиши короткое описание (цвет, материал и т.д.) или нажми «Пропустить».",
                         reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⏩ Пропустить")]], resize_keyboard=True))
    await state.set_state(AddClothesStates.waiting_description)

@router.message(AddClothesStates.waiting_description, F.text)
async def add_clothes_description(message: Message, state: FSMContext):
    logger.info(f"Описание: {message.text}")
    description = message.text if message.text != "⏩ Пропустить" else None
    user_id = str(message.from_user.id)
    data = await state.get_data()
    photo_file_id = data.get('photo_file_id')
    clothing_type = data.get('clothing_type')

    file_info = await bot.get_file(photo_file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_info.file_path}"
    image_url = await upload_wardrobe_image(user_id, file_url)
    if not image_url:
        await message.answer("❌ Не удалось сохранить фото. Попробуй позже.")
        await state.clear()
        return

    add_wardrobe_item(user_id, image_url, clothing_type, description)
    await message.answer("✅ Вещь добавлена в гардероб!", reply_markup=get_main_keyboard())
    await state.clear()

# ==================== НОВЫЙ ВАРИАНТ ГАРДЕРОБА (АЛЬБОМ + КНОПКИ) ====================
@router.message(Command("my_wardrobe"))
async def cmd_my_wardrobe(message: Message):
    logger.info(f"Команда /my_wardrobe от {message.from_user.id}")
    user_id = str(message.from_user.id)
    items = get_wardrobe_items(user_id)
    if not items:
        await message.answer("📭 Твой гардероб пуст. Добавь вещи командой /add_clothes", reply_markup=get_main_keyboard())
        return

    # Отправляем альбом с фото (группируем по 10)
    batch_size = 10
    for i in range(0, len(items), batch_size):
        batch = items[i:i+batch_size]
        media = []
        for j, item in enumerate(batch):
            caption = f"<b>{item['clothing_type'] or 'Вещь'}</b>\n{item['description'] or ''}" if j == 0 else ""
            media.append(InputMediaPhoto(media=item['image_url'], caption=caption, parse_mode="HTML"))
        await bot.send_media_group(chat_id=message.chat.id, media=media)

    # Формируем отдельное сообщение со списком кнопок для каждой вещи
    keyboard_buttons = []
    for item in items:
        row = [
            InlineKeyboardButton(text=f"❌ Удалить {item['clothing_type'] or 'вещь'}", callback_data=f"del_wardrobe_{item['id']}"),
            InlineKeyboardButton(text=f"🧥 Примерь {item['clothing_type'] or 'вещь'}", callback_data=f"tryon_{item['id']}")
        ]
        keyboard_buttons.append(row)
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer("🗂 Вот все вещи из твоего гардероба. Выбери действие:", reply_markup=markup)

@router.callback_query(lambda c: c.data and c.data.startswith("del_wardrobe_"))
async def delete_wardrobe_callback(callback: CallbackQuery):
    item_id = int(callback.data.split("_")[2])
    user_id = str(callback.from_user.id)
    delete_wardrobe_item(user_id, item_id)
    await callback.answer("Вещь удалена из гардероба")
    # Удаляем сообщение с кнопками, чтобы пользователь не кликал по удалённой вещи
    await callback.message.delete()
    await callback.message.answer("Гардероб обновлён. Нажми /my_wardrobe для просмотра.")

@router.callback_query(lambda c: c.data and c.data.startswith("tryon_"))
async def tryon_wardrobe_callback(callback: CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split("_")[1])
    user_id = str(callback.from_user.id)
    items = get_wardrobe_items(user_id)
    cloth_url = None
    for item in items:
        if item['id'] == item_id:
            cloth_url = item['image_url']
            break
    if not cloth_url:
        await callback.message.answer("❌ Вещь не найдена.")
        await callback.answer()
        return
    await state.update_data(cloth_url=cloth_url)
    await callback.message.answer("📸 Теперь отправь фото человека (в полный рост) для примерки.")
    await state.set_state(TryOnStates.waiting_person_photo)
    await callback.answer()

# Обработчик получения фото человека для примерки
@router.message(TryOnStates.waiting_person_photo, F.photo)
async def tryon_person_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    cloth_url = data.get('cloth_url')
    if not cloth_url:
        await message.answer("❌ Ошибка: вещь не найдена. Начните заново через /my_wardrobe.")
        await state.clear()
        return
    # Здесь нужно отправить запрос к FASHN API или перенаправить к боту примерки.
    # Для простоты перенаправим пользователя к отдельному боту-помощнику (как у вас было ранее)
    await message.answer(
        "👕 <b>Виртуальная примерка</b>\n\n"
        "Для примерки этой вещи перейди к моему специальному боту-помощнику — @VirtuLookBot.\n"
        "Просто отправь ему это фото и своё фото, и он покажет результат!\n\n"
        "👉 [Нажми сюда, чтобы перейти к @VirtuLookBot](https://t.me/VirtuLookBot)",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    await state.clear()

# Обработчик для кнопки "Найти похожее" (заглушка)
@router.callback_query(lambda c: c.data and c.data.startswith("find_"))
async def find_similar_callback(callback: CallbackQuery):
    await callback.answer("Функция поиска похожих вещей в разработке", show_alert=True)

@router.message(Command("look"))
async def cmd_look(message: Message):
    logger.info(f"Команда /look от {message.from_user.id}")
    user_id = str(message.from_user.id)
    items = get_wardrobe_items(user_id)
    if len(items) < 2:
        await message.answer("Добавь хотя бы 2 вещи в гардероб командой /add_clothes")
        return
    selected = random.sample(items, min(3, len(items)))
    descriptions = [f"{item['clothing_type'] or 'Вещь'}: {item['description'] or 'без описания'}" for item in selected]
    prompt = f"Ты стилист. Из этих вещей: {', '.join(descriptions)}. Составь стильный образ на сегодня. Напиши кратко, что надеть и почему."
    try:
        answer = await gemini.generate_text(prompt)
        await message.answer(f"✨ <b>Твой образ на сегодня</b>\n\n{answer}", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка генерации образа: {e}")
        await message.answer("Не удалось составить образ, попробуй позже.")
