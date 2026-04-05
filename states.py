from aiogram.fsm.state import State, StatesGroup

class ProfileStates(StatesGroup):
    waiting_gender = State()
    waiting_style = State()
    waiting_figure = State()
    waiting_color = State()
    waiting_budget = State()
    waiting_height = State()
    waiting_age = State()
    waiting_size = State()
