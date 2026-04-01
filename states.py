from aiogram.fsm.state import State, StatesGroup

class ProfileStates(StatesGroup):
    waiting_gender = State()
    waiting_style = State()

class FavoritesStates(StatesGroup):
    browsing = State()   # навигация по избранному
