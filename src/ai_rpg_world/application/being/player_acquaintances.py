"""ゲームのプレイヤーと、その Being の知り合いの記録をつなぐ。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from ai_rpg_world.being.domain.acquaintance import Acquaintance, AcquaintanceRepository
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.repository.memory_turn_reader import (
    MemoryTurnReader,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput

_logger = logging.getLogger(__name__)

_TYPE_ENTITY_ENTERED_SPOT = "entity_entered_spot"


class PlayerAcquaintances:
    """記録は Being の持ち物で、鍵に環境の名前と相手の名前の文だけを使う。

    プレイヤー番号から Being を引くのと、名前からプレイヤー番号を引くのは、
    ゲームの側にあるこの部品だけが行う。
    """

    def __init__(
        self,
        *,
        store: AcquaintanceRepository,
        being_id_of: Callable[[PlayerId], BeingId | None],
        turn_reader: MemoryTurnReader,
        environment_name: str,
        names_by_player_id: Mapping[int, str],
    ) -> None:
        self._store = store
        self._being_id_of = being_id_of
        self._turn_reader = turn_reader
        self._environment_name = environment_name
        self._names_by_player_id = dict(names_by_player_id)
        self._player_id_by_name = {
            name: pid for pid, name in self._names_by_player_id.items()
        }
        self._unresolved_warned: set[int] = set()

    def record_meeting(self, player_id: PlayerId, name: str) -> None:
        if name == self._names_by_player_id.get(player_id.value):
            return
        being_id = self._resolve(player_id)
        if being_id is None:
            return
        self._store.record_meeting(
            being_id,
            environment_name=self._environment_name,
            name=name,
            turn=self._turn_reader.current_turn(being_id),
        )

    def find(self, player_id: PlayerId, name: str) -> Acquaintance | None:
        being_id = self._resolve(player_id)
        if being_id is None:
            return None
        return self._store.find(
            being_id, environment_name=self._environment_name, name=name
        )

    def recently_met_names(
        self, player_id: PlayerId, *, within_turns: int
    ) -> tuple[str, ...]:
        being_id = self._resolve(player_id)
        if being_id is None:
            return ()
        now = self._turn_reader.current_turn(being_id)
        return tuple(
            a.name
            for a in self._store.list_by_being(being_id)
            if a.environment_name == self._environment_name
            and 0 <= now - a.last_met_turn <= within_turns
        )

    def on_observation(self, recipient: PlayerId, output: ObservationOutput) -> None:
        """入ってきた人とその場にいた受け手は、互いの姿を見ている。

        入ってきた本人には自分の到着の観測が届かないので、受け手への観測から
        両方の記録を残す。名前の伏せられた観測では、どちらも相手を見ていない。
        """
        try:
            structured = output.structured or {}
            if structured.get("type") != _TYPE_ENTITY_ENTERED_SPOT:
                return
            actor = structured.get("actor")
            if not isinstance(actor, str) or not actor.strip():
                return
            self.record_meeting(recipient, actor)
            actor_id = self._player_id_by_name.get(actor)
            recipient_name = self._names_by_player_id.get(recipient.value)
            if actor_id is not None and recipient_name is not None:
                self.record_meeting(PlayerId(actor_id), recipient_name)
        except Exception:
            _logger.exception(
                "会った記録を残せなかった (recipient=%s)", recipient.value
            )

    def _resolve(self, player_id: PlayerId) -> BeingId | None:
        being_id = self._being_id_of(player_id)
        if being_id is None and player_id.value not in self._unresolved_warned:
            self._unresolved_warned.add(player_id.value)
            _logger.warning(
                "player_id=%s に結び付く Being が無く、会った記録を読み書きしない "
                "(この player については以後再警告しない)",
                player_id.value,
            )
        return being_id


__all__ = ["PlayerAcquaintances"]
