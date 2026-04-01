from aiogram.fsm.state import State, StatesGroup

class ProfileStates(StatesGroup):
    waiting_gender = State()   # ожидаем выбор пола
    waiting_style = State()    # ожидаем выбор стиля
