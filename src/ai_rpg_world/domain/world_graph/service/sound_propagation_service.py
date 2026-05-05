from __future__ import annotations

from collections import deque
from typing import Dict, List, Tuple

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.enum.sound_clarity import SoundClarityEnum
from ai_rpg_world.domain.world_graph.enum.sound_volume import SoundVolumeEnum
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.sound_recipient import SoundRecipient

# この値未満の経路累積では「聞こえない」として打ち切る
_MIN_AUDIBLE_ACCUM = 0.02


def _clarity_rank(c: SoundClarityEnum) -> int:
    return {SoundClarityEnum.CLEAR: 3, SoundClarityEnum.MUFFLED: 2, SoundClarityEnum.FAINT: 1}[c]


class SoundPropagationService:
    """スポットグラフ上の音の届き方（接続の音透過率・ホップ数）。"""

    @staticmethod
    def clarity_for_hops_and_accum(hops: int, path_accum: float) -> SoundClarityEnum:
        """ホップ数と経路上の透過率の積から明瞭さを決める。"""
        if hops == 0:
            return SoundClarityEnum.CLEAR
        if hops == 1:
            if path_accum >= 0.35:
                return SoundClarityEnum.MUFFLED
            return SoundClarityEnum.FAINT
        return SoundClarityEnum.FAINT

    def resolve_recipients(
        self,
        speaker_entity_id: EntityId,
        volume: SoundVolumeEnum,
        graph: SpotGraphAggregate,
    ) -> Tuple[SoundRecipient, ...]:
        """話者の音量に応じ、聞こえるエンティティと明瞭さの一覧を返す。"""
        speaker_spot = graph.get_entity_spot(speaker_entity_id)
        max_hops = volume.max_hops()

        best_clarity: Dict[EntityId, SoundClarityEnum] = {}

        def merge(eid: EntityId, clarity: SoundClarityEnum) -> None:
            if eid not in best_clarity or _clarity_rank(clarity) > _clarity_rank(best_clarity[eid]):
                best_clarity[eid] = clarity

        frontier: deque[Tuple[SpotId, float]] = deque([(speaker_spot, 1.0)])

        for h in range(max_hops + 1):
            next_frontier: deque[Tuple[SpotId, float]] = deque()
            while frontier:
                spot, accum_to_spot = frontier.popleft()
                clarity = self.clarity_for_hops_and_accum(h, accum_to_spot)
                presence = graph.presence_at(spot)
                for eid in presence.present_entity_ids:
                    merge(eid, clarity)

                if h >= max_hops:
                    continue
                for conn in graph.iter_outgoing_connections_from(spot):
                    # passage がある接続では passage の透過率が source of truth。
                    # effective_sound_permeability 経由で読むことで、将来の
                    # 方向性付き/動的変調を 1 箇所に集約できるようにする。
                    na = accum_to_spot * conn.effective_sound_permeability
                    if na < _MIN_AUDIBLE_ACCUM:
                        continue
                    next_frontier.append((conn.to_spot_id, na))
            frontier = next_frontier

        out: List[SoundRecipient] = []
        for eid, clarity in best_clarity.items():
            spot_id = graph.get_entity_spot(eid)
            out.append(SoundRecipient(entity_id=eid, spot_id=spot_id, clarity=clarity))
        return tuple(out)

    def clarity_for_listener(
        self,
        speaker_entity_id: EntityId,
        listener_entity_id: EntityId,
        volume: SoundVolumeEnum,
        graph: SpotGraphAggregate,
    ) -> SoundClarityEnum | None:
        """指定エンティティの聞き取り明瞭さ。届かなければ None。"""
        for r in self.resolve_recipients(speaker_entity_id, volume, graph):
            if r.entity_id == listener_entity_id:
                return r.clarity
        return None
