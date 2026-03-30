from aiogram.fsm.state import State, StatesGroup


class AdminIssueState(StatesGroup):
    waiting_target = State()
