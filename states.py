from aiogram.fsm.state import State, StatesGroup

class ProfileStates(StatesGroup):
    waiting_gender = State()
    waiting_style = State()

class WardrobeStates(StatesGroup):
    waiting_for_photo = State()       # ожидаем фото
    waiting_clothing_type = State()   # ожидаем ввод типа одежды
    waiting_description = State()     # ожидаем ввод описания

class TryOnStates(StatesGroup):
    waiting_person_photo = State()
    waiting_clothing_selection = State()
