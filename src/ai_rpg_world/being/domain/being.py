"""Being 集約。経験を持つ主体で、世界や run を跨いで残る。

記憶は集約に入れず、``BeingId`` をキーにした保存先がそれぞれ持つ。記憶の保存先は書き込みが多く、集約に閉じると
ロックで競合するため。
"""

from __future__ import annotations

from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.domain.being.exception.being_exceptions import BeingAlreadyAttachedException
from ai_rpg_world.domain.being.value_object.being_attachment import BeingAttachment
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.eventing import AggregateRoot, DomainEvent


class Being(AggregateRoot[DomainEvent]):
    def __init__(
        self,
        being_id: BeingId,
        persona: Persona,
        attachment: BeingAttachment | None = None,
    ) -> None:
        super().__init__()
        if not isinstance(being_id, BeingId):
            raise TypeError(f"being_id must be BeingId, got {type(being_id).__name__}")
        if not isinstance(persona, Persona):
            raise TypeError(f"persona must be Persona, got {type(persona).__name__}")
        if attachment is not None and not isinstance(attachment, BeingAttachment):
            raise TypeError(f"attachment must be BeingAttachment or None, got {type(attachment).__name__}")
        self._being_id = being_id
        self._persona = persona
        self._attachment: BeingAttachment | None = attachment

    @property
    def being_id(self) -> BeingId:
        return self._being_id

    @property
    def persona(self) -> Persona:
        return self._persona

    @property
    def attachment(self) -> BeingAttachment | None:
        return self._attachment

    @property
    def is_attached(self) -> bool:
        return self._attachment is not None

    def attach(self, attachment: BeingAttachment) -> None:
        """乗り換えるときは先に ``detach`` する。同時に入れる環境は 1 つまで。"""
        if not isinstance(attachment, BeingAttachment):
            raise TypeError(f"attachment must be BeingAttachment, got {type(attachment).__name__}")
        if self._attachment is not None:
            raise BeingAlreadyAttachedException(
                f"Being({self._being_id}) is already attached to {self._attachment}; detach first to switch"
            )
        self._attachment = attachment

    def detach(self) -> BeingAttachment | None:
        """解除前の値を返す。未 attach なら None。離れても記憶は Being に残る。"""
        previous = self._attachment
        self._attachment = None
        return previous

    def __repr__(self) -> str:
        return f"Being(being_id={self._being_id!r}, persona={self._persona!r}, attachment={self._attachment!r})"


__all__ = ["Being"]
