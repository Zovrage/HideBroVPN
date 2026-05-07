from aiogram.fsm.state import State, StatesGroup


class AdminIssueState(StatesGroup):
    waiting_target = State()
    waiting_device_limit = State()
    waiting_issue_months = State()
    waiting_extend_target = State()
    waiting_extend_subscription = State()
    waiting_extend_months = State()
    waiting_broadcast = State()
