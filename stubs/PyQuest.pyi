# PyQuest.pyi - Type stub for PyQuest (PyBind11 bindings)

class PyQuest:
    def __init__(self) -> None: ...
    def set_active_quest_id(self, quest_id: int) -> None: ...
    def get_active_quest_id(self) -> int: ...
    def abandon_quest_id(self, quest_id: int) -> None: ...
    def is_quest_completed(self, quest_id: int) -> bool: ...
    def is_quest_primary(self, quest_id: int) -> bool: ...
