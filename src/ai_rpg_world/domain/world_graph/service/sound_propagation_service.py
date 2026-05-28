from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Tuple

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
        """話者の音量に応じ、聞こえるエンティティと明瞭さ・到来方向の一覧を返す。

        Issue #269: BFS の各 frontier に「最後に通った接続の name + 到来元の
        spot id」を持たせ、listener に届くときに記録する。同じ listener に
        複数経路で届く場合は最も明瞭なものを採用し、同 clarity なら BFS で
        先に到達した経路 (= より短い経路) を採用する。
        """
        speaker_spot = graph.get_entity_spot(speaker_entity_id)
        max_hops = volume.max_hops()

        # eid → (clarity, source_connection_name, source_adjacent_spot_id)
        best: Dict[
            EntityId,
            Tuple[SoundClarityEnum, Optional[str], Optional[SpotId]],
        ] = {}

        def merge(
            eid: EntityId,
            clarity: SoundClarityEnum,
            conn_name: Optional[str],
            from_spot: Optional[SpotId],
        ) -> None:
            current = best.get(eid)
            if current is None or _clarity_rank(clarity) > _clarity_rank(current[0]):
                best[eid] = (clarity, conn_name, from_spot)

        # (spot, accum, last_hop_connection_name, last_hop_from_spot_id)
        # last_hop_* は speaker_spot 自身では None。
        frontier: deque[
            Tuple[SpotId, float, Optional[str], Optional[SpotId]]
        ] = deque([(speaker_spot, 1.0, None, None)])

        for h in range(max_hops + 1):
            next_frontier: deque[
                Tuple[SpotId, float, Optional[str], Optional[SpotId]]
            ] = deque()
            while frontier:
                spot, accum_to_spot, last_hop_name, last_hop_from = frontier.popleft()
                clarity = self.clarity_for_hops_and_accum(h, accum_to_spot)
                presence = graph.presence_at(spot)
                for eid in presence.present_entity_ids:
                    merge(eid, clarity, last_hop_name, last_hop_from)

                if h >= max_hops:
                    continue
                for conn in graph.iter_outgoing_connections_from(spot):
                    na = accum_to_spot * conn.passage.sound_permeability
                    if na < _MIN_AUDIBLE_ACCUM:
                        continue
                    # 次フロンティアでは「今この conn を通って到達した」を記録。
                    # listener の現在スポットに着いたときの conn が direction
                    # として使われる (= last hop)。
                    next_frontier.append((conn.to_spot_id, na, conn.name, spot))
            frontier = next_frontier

        out: List[SoundRecipient] = []
        for eid, (clarity, conn_name, from_spot) in best.items():
            spot_id = graph.get_entity_spot(eid)
            out.append(
                SoundRecipient(
                    entity_id=eid,
                    spot_id=spot_id,
                    clarity=clarity,
                    source_connection_name=conn_name,
                    source_adjacent_spot_id=from_spot,
                )
            )
        return tuple(out)

    def clarity_for_listener(
        self,
        speaker_entity_id: EntityId,
        listener_entity_id: EntityId,
        volume: SoundVolumeEnum,
        graph: SpotGraphAggregate,
    ) -> SoundClarityEnum | None:
        """指定エンティティの聞き取り明瞭さ。届かなければ None。"""
        outcome = self.outcome_for_listener(
            speaker_entity_id, listener_entity_id, volume, graph
        )
        return outcome.clarity if outcome is not None else None

    def outcome_for_listener(
        self,
        speaker_entity_id: EntityId,
        listener_entity_id: EntityId,
        volume: SoundVolumeEnum,
        graph: SpotGraphAggregate,
    ) -> Optional[SoundRecipient]:
        """指定 listener に届いた SoundRecipient (clarity + 方向) を返す。

        Issue #269: formatter が方向情報を prose に含めるための単一エントリ。
        届かなければ None。
        """
        for r in self.resolve_recipients(speaker_entity_id, volume, graph):
            if r.entity_id == listener_entity_id:
                return r
        return None
