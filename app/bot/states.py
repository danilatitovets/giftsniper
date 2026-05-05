from aiogram.fsm.state import State, StatesGroup


class CheckNftFlow(StatesGroup):
    waiting_input = State()
