from aiogram.fsm.state import State, StatesGroup


class AdminIssueState(StatesGroup):
    waiting_target = State()
    waiting_device_limit = State()
    waiting_days = State()
    waiting_broadcast = State()
