from abc import ABC, abstractmethod


class ActionResult(ABC):
    def __init__(self, success: bool, message: str):
        self.success = success
        self.message = message

    @abstractmethod
    def to_feedback_message(self, player_name: str) -> str:
        pass


class ErrorActionResult(ActionResult):
    def __init__(self, error_message: str):
        super().__init__(False, error_message)
        self.error_type = "GenericError"

    def to_feedback_message(self, player_name: str) -> str:
        return f"行動の実行中にエラーが発生しました: {self.message}"