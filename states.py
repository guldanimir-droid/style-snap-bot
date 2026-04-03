from aiogram.fsm.state import State, StatesGroup

class ProfileStates(StatesGroup):
    waiting_gender = State()
    waiting_style = State()

class WardrobeStates(StatesGroup):
    waiting_for_photo = State()
    waiting_clothing_type = State()
    waiting_description = State()
