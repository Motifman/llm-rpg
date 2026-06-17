"""Encounter Memory の application 層 interface。

Encounter Memory は player ごとに「自分が遭遇した対象 (entity / spot / event-type)」
の familiarity 信号を保持する。observation pipeline の入口で照合し、
prompt の【現在地と周囲】section に「初対面」「再会」等の注記を出すために使う。

詳細は docs/memory_system/perception_memory_join_design.md を参照。

設計判断:

- ``observe(player_id, key, current_tick)`` は upsert セマンティクス。既存 record
  があれば ``observed_again`` で更新、無ければ ``first`` で初期化する。呼出側は
  「初回かどうか」を判定する必要がない (= 返り値の ``is_first`` を見るだけで判る)
- ``lookup`` は存在しない場合 ``None`` を返す。「まだ会ったことがない」を表現する
  純粋な query API として使える
- ``get_records_for(player_id)`` は player ごとの全 record を読み取り専用で返す。
  snapshot codec が iterate するために使う。``get_*`` 接頭辞は既存 memory
  interface (ISlidingWindowMemory.get_recent 等) との命名一貫性のため
"""

from __future__ import annotations

from typing import Mapping, Optional, Protocol, runtime_checkable

from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_record import (
    EncounterRecord,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@runtime_checkable
class IEncounterMemory(Protocol):
    """player ごとの encounter (familiarity) 記録の interface。"""

    def observe(
        self,
        player_id: PlayerId,
        key: EncounterKey,
        current_tick: int,
    ) -> EncounterRecord:
        """``player_id`` が ``key`` を ``current_tick`` で観測したことを記録する。

        - 既存 record があれば ``observed_again(now_tick=current_tick)`` で更新
        - 無ければ ``EncounterRecord.first(now_tick=current_tick)`` で初期化

        返り値は更新後 (= 現在) の record。``record.is_first`` で初回判定できる。
        """
        ...

    def lookup(
        self,
        player_id: PlayerId,
        key: EncounterKey,
    ) -> Optional[EncounterRecord]:
        """``player_id`` が ``key`` を過去に観測したことがあれば record を返す。

        観測していない場合は ``None``。「まだ会ったことがない」を表現する。
        """
        ...

    def get_records_for(
        self,
        player_id: PlayerId,
    ) -> Mapping[EncounterKey, EncounterRecord]:
        """``player_id`` の全 encounter record を返す (読み取り専用)。

        snapshot codec / debug 表示用。observation pipeline の hot path では
        ``lookup`` を使う想定。
        """
        ...


__all__ = ["IEncounterMemory"]
