from aiogram.fsm.state import State, StatesGroup

class RegisterState(StatesGroup):
    waiting_for_birthday = State()
    confirm_birthday = State()
    waiting_for_timezone = State()
    confirm_timezone = State()
    finished = State()

class SettingsState(StatesGroup):
    waiting_for_new_birthday = State()
    waiting_for_new_timezone = State()
    confirm_new_timezone = State()