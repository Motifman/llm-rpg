"""ドメインイベントを受けて裏のスレッドで仕事をし、結果を宛先のスレッドで反映するハンドラの基底。"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from ai_rpg_world.eventing.domain_event import DomainEvent

_Event = TypeVar("_Event", bound=DomainEvent)
_Command = TypeVar("_Command")
_Result = TypeVar("_Result")


class AsyncEventHandler(ABC, Generic[_Event, _Command, _Result]):
    """3 つの段を、それぞれ決まったスレッドで呼ぶ。

    裏のスレッドで動く ``handle`` は、``prepare`` が作ったコマンドだけを受け取る。保存先や実行環境の
    変わる状態に、裏のスレッドから触らないようにするため。
    """

    @abstractmethod
    def prepare(self, event: _Event) -> _Command:
        """配送器 (``EventDispatcher``) にイベントを渡したスレッドで、イベントから値を取り出し、要る材料を集めてコマンドを作る。"""

    @abstractmethod
    def handle(self, command: _Command) -> _Result:
        """裏のスレッドで、コマンドを受けて仕事をする。"""

    @abstractmethod
    def apply(self, result: _Result) -> None:
        """宛先の結果を反映するスレッド (Being ならそのターンの始め) で、結果を反映する。"""
