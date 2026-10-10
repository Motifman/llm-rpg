"""ゲームのプレイヤーと、その Being の知り合いの記録をつなぐ。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from ai_rpg_world.being.application.known_people import render_known_people
from ai_rpg_world.being.contract import EnvironmentEntry
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
        if not environment_name.strip():
            raise ValueError("environment_name must be non-blank")
        names = list(names_by_player_id.values())
        duplicated = sorted({n for n in names if names.count(n) > 1})
        if duplicated:
            raise ValueError(
                f"participants share a name, so a name cannot tell who met whom: {duplicated}"
            )
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

    def receive_entry(self, player_id: PlayerId, entry: EnvironmentEntry) -> None:
        """紹介はプロンプトの前提なので、渡せないときは黙って捨てずに止める。"""
        if entry.environment_name != self._environment_name:
            raise ValueError(
                f"entry is for {entry.environment_name!r}, "
                f"but acquaintances are kept for {self._environment_name!r}"
            )
        being_id = self._resolve(player_id)
        if being_id is None:
            if entry.introductions:
                raise ValueError(
                    f"player_id={player_id.value} has no Being to receive introductions"
                )
            return
        turn = self._turn_reader.current_turn(being_id)
        for introduction in entry.introductions:
            self._store.record_introduction(
                being_id,
                environment_name=self._environment_name,
                name=introduction.name,
                turn=turn,
                relation_note=introduction.relation_note,
            )

    def known_people_text(self, player_id: PlayerId) -> str:
        being_id = self._resolve(player_id)
        if being_id is None:
            return ""
        return render_known_people(
            self._store.list_by_being(being_id),
            environment_name=self._environment_name,
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
            and a.last_met_turn is not None
            and 0 <= now - a.last_met_turn <= within_turns
        )

    def view_for(self, recipient: PlayerId, output: ObservationOutput) -> ObservationOutput:
        """受け手の記録に入れる版を選ぶ。記録したあとで相手を知っても、記録は書き換えない。"""
        view = output.if_subject_unknown
        if output.subject_name is None or view is None:
            return output
        try:
            known = self.find(recipient, output.subject_name) is not None
        except Exception:
            # 引けないときは伏せる側へ倒す。名前は、あとで記録から消せない。
            _logger.exception(
                "知り合いの記録を引けず、話し手の名前を伏せて記録する (recipient=%s)",
                recipient.value,
            )
            known = False
        return output.as_subject_known() if known else output.as_subject_unknown()

    def on_observation(self, recipient: PlayerId, output: ObservationOutput) -> None:
        """入ってきた人とその場にいた受け手は、互いの姿を見ている。

        入ってきた本人には自分の到着の観測が届かないので、受け手への観測から
        両方の記録を残す。名前の伏せられた観測では、どちらも相手を見ていない。
        参加者に無い名前 (モンスター、名前を引けなかったときの代わりの名前) は
        人として記録しない。
        """
        structured = output.structured or {}
        if structured.get("type") != _TYPE_ENTITY_ENTERED_SPOT:
            return
        actor = structured.get("actor")
        if not isinstance(actor, str):
            return
        actor = actor.strip()
        actor_id = self._player_id_by_name.get(actor)
        recipient_name = self._names_by_player_id.get(recipient.value)
        if actor_id is None or recipient_name is None:
            return
        self._record_safely(recipient, actor)
        self._record_safely(PlayerId(actor_id), recipient_name)

    def _record_safely(self, player_id: PlayerId, name: str) -> None:
        try:
            self.record_meeting(player_id, name)
        except Exception:
            _logger.exception(
                "会った記録を残せなかった (player_id=%s, name=%s)",
                player_id.value,
                name,
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
