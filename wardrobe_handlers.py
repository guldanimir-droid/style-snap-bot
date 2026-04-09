import asyncio
import logging
import random
from aiogram import F, Router, Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

from database import add_wardrobe_item, get_wardrobe_items, delete_wardrobe_item
from supabase_utils import upload_wardrobe_image
from config import TELEGRAM_BOT_TOKEN
from gigachat_client import GigaChatClientWrapper
from config import GIGACHAT_CLIENT_ID, GIGACHAT_SECRET

logger = logging.getLogger(__name__)
router = Router()
bot = Bot(token=TELEGRAM_BOT_TOKEN)
gemini = GigaChatClientWrapper(
    client_id=GIGACHAT_CLIENT_ID,
    client_secret=GIGACHAT_SECRET
)

class AddClothesStates(StatesGroup):
    waiting_photo = State()
    waiting_type = State()
    waiting_description = State()

@router.message(Command("add_clothes"))
async def cmd_add_clothes(message: Message, state: FSMContext):
    await message.answer("📸 Отправь фотографию вещи, которую хочешь добавить в гардероб.")
    await state.set_state(AddClothesStates.waiting_photo)

@router.message(AddClothesStates.waiting_photo, F.photo)
async def add_clothes_photo(message: Message, state: FSMContext):
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
    text = message.text
    if text == "⏩ Пропустить":
        clothing_type = None
    else:
        clothing_type = text.strip()
    await state.update_data(clothing_type=clothing_type)
    await message.answer("Теперь напиши короткое описание (цвет, материал и т.д.) или нажми «Пропустить».",
                         reply_markup=ReplyKeyboardMarkup.from_button(KeyboardButton(text="⏩ Пропустить"), resize_keyboard=True))
    await state.set_state(AddClothesStates.waiting_description)

@router.message(AddClothesStates.waiting_description, F.text)
async def add_clothes_description(message: Message, state: FSMContext):
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
    from bot import get_main_keyboard
    await message.answer("✅ Вещь добавлена в гардероб!", reply_markup=get_main_keyboard())
    await state.clear()

@router.message(Command("my_wardrobe"))
async def cmd_my_wardrobe(message: Message):
    user_id = str(message.from_user.id)
    items = get_wardrobe_items(user_id)
    if not items:
        await message.answer("📭 Твой гардероб пуст. Добавь вещи командой /add_clothes")
        return
    for item in items:
        buttons = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🧥 Примерь", callback_data=f"tryon_{item['id']}"),
                InlineKeyboardButton(text="🔍 Найти похожее", callback_data=f"find_{item['id']}"),
                InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_wardrobe_{item['id']}")
            ]
        ])
        caption = f"<b>{item['clothing_type'] or 'Вещь'}</b>\n{item['description'] or ''}"
        try:
            await bot.send_photo(chat_id=message.chat.id, photo=item['image_url'],
                                 caption=caption, reply_markup=buttons, parse_mode="HTML")
        except TelegramBadRequest as e:
            logger.error(f"Не удалось отправить фото {item['image_url']}: {e}")
            # Можно также удалить запись с битой ссылкой
            # delete_wardrobe_item(user_id, item['id'])
            await message.answer(f"⚠️ Не удалось показать одну из вещей (возможно, фото недоступно). Попробуйте удалить её и добавить заново.")

@router.callback_query(lambda c: c.data.startswith("del_wardrobe_"))
async def delete_wardrobe_callback(callback: CallbackQuery):
    item_id = int(callback.data.split("_")[2])
    user_id = str(callback.from_user.id)
    delete_wardrobe_item(user_id, item_id)
    await callback.answer("Вещь удалена из гардероба")
    await callback.message.delete()

@router.callback_query(lambda c: c.data.startswith("tryon_"))
async def tryon_wardrobe_callback(callback: CallbackQuery):
    await callback.answer("Функция примерки скоро появится! Пока воспользуйся @VirtuLookBot", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("find_"))
async def find_similar_callback(callback: CallbackQuery):
    await callback.answer("Функция поиска похожих вещей в разработке", show_alert=True)

@router.message(Command("look"))
async def cmd_look(message: Message):
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
