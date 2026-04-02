from aiogram.fsm.state import State, StatesGroup

class ProfileStates(StatesGroup):
    waiting_gender = State()   # ожидаем выбор пола
    waiting_style = State()    # ожидаем выбор стиля

class WardrobeStates(StatesGroup):
    waiting_for_photo = State()   # ожидаем фото для добавления в гардероб

class TryOnStates(StatesGroup):
    waiting_person_photo = State()       # ожидаем фото человека
    waiting_clothing_selection = State() # ожидаем выбора одежды из гардероба
