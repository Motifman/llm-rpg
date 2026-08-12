"""倒れた身体の場所と時刻を、行為主体の現在地から独立して保持する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


@dataclass(frozen=True)
class FallenBodyRecord:
    """一度倒れた身体が残る場所と、その出来事が起きた時刻。"""

    player_id: PlayerId
    spot_id: SpotId
    downed_at_tick: WorldTick


class FallenBodyRegistry:
    """倒れた身体を player ごとに一件だけ保持する世界状態。"""

    def __init__(self) -> None:
        self._records: dict[PlayerId, FallenBodyRecord] = {}

    def record(
        self,
        player_id: PlayerId,
        spot_id: SpotId,
        downed_at_tick: WorldTick,
    ) -> FallenBodyRecord:
        """初回の倒れた場所を記録し、同じ down の重複通知では動かさない。"""
        existing = self._records.get(player_id)
        if existing is not None:
            return existing
        record = FallenBodyRecord(player_id, spot_id, downed_at_tick)
        self._records[player_id] = record
        return record

    def remove(self, player_id: PlayerId) -> None:
        """蘇生した player の身体記録を取り除く。"""
        self._records.pop(player_id, None)

    def clear(self) -> None:
        """会議後に、世界に残っているすべての身体記録を取り除く。"""
        self._records.clear()

    def find(self, player_id: PlayerId) -> FallenBodyRecord | None:
        return self._records.get(player_id)

    def records_at(self, spot_id: SpotId) -> tuple[FallenBodyRecord, ...]:
        return tuple(
            record
            for _, record in sorted(
                self._records.items(), key=lambda item: int(item[0])
            )
            if record.spot_id == spot_id
        )

    def snapshot(self) -> dict[PlayerId, FallenBodyRecord]:
        return dict(self._records)

    def replace_all(self, records: Mapping[PlayerId, FallenBodyRecord]) -> None:
        """callback を起こさず、検証済みの復元値で全体を置き換える。"""
        normalized: dict[PlayerId, FallenBodyRecord] = {}
        for player_id, record in records.items():
            if player_id != record.player_id:
                raise ValueError(
                    "fallen body record key does not match record.player_id: "
                    f"key={int(player_id)} record={int(record.player_id)}"
                )
            normalized[player_id] = record
        self._records = normalized


__all__ = ["FallenBodyRecord", "FallenBodyRegistry"]
