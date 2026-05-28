"""SoundPropagationService のユニットテスト"""

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.sound_clarity import SoundClarityEnum
from ai_rpg_world.domain.world_graph.enum.sound_volume import SoundVolumeEnum
from ai_rpg_world.domain.world_graph.service.sound_propagation_service import (
    SoundPropagationService,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _node(i: int) -> SpotNode:
    return SpotNode(
        spot_id=SpotId.create(i),
        name=f"S{i}",
        description="d",
        category=SpotCategoryEnum.OTHER,
        parent_id=None,
    )


def _conn(
    cid: int,
    a: int,
    b: int,
    *,
    perm: float = 1.0,
    name: str = "c",
) -> SpotConnection:
    return SpotConnection(
        connection_id=ConnectionId.create(cid),
        from_spot_id=SpotId.create(a),
        to_spot_id=SpotId.create(b),
        name=name,
        description="",
        travel_ticks=1,
        is_bidirectional=False,
        passage=Passage.open(sound_permeability=perm),
    )


class TestSoundPropagationService:
    def test_whisper_only_same_spot(self) -> None:
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(_conn(1, 1, 2, perm=1.0))
        g.place_entity(EntityId.create(1), SpotId.create(1))
        g.place_entity(EntityId.create(2), SpotId.create(2))
        svc = SoundPropagationService()
        rec = svc.resolve_recipients(EntityId.create(1), SoundVolumeEnum.WHISPER, g)
        ids = {r.entity_id for r in rec}
        assert ids == {EntityId.create(1)}

    def test_normal_reaches_neighbor_muffled(self) -> None:
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(_conn(1, 1, 2, perm=0.5))
        g.place_entity(EntityId.create(1), SpotId.create(1))
        g.place_entity(EntityId.create(2), SpotId.create(2))
        svc = SoundPropagationService()
        rec = svc.resolve_recipients(EntityId.create(1), SoundVolumeEnum.NORMAL, g)
        by_eid = {r.entity_id: r.clarity for r in rec}
        assert by_eid[EntityId.create(1)] == SoundClarityEnum.CLEAR
        assert by_eid[EntityId.create(2)] == SoundClarityEnum.MUFFLED

    def test_normal_neighbor_low_perm_is_faint(self) -> None:
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(_conn(1, 1, 2, perm=0.2))
        g.place_entity(EntityId.create(1), SpotId.create(1))
        g.place_entity(EntityId.create(2), SpotId.create(2))
        svc = SoundPropagationService()
        rec = svc.resolve_recipients(EntityId.create(1), SoundVolumeEnum.NORMAL, g)
        by_eid = {r.entity_id: r.clarity for r in rec}
        assert by_eid[EntityId.create(2)] == SoundClarityEnum.FAINT

    def test_clarity_for_listener(self) -> None:
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(_conn(1, 1, 2, perm=0.5))
        g.place_entity(EntityId.create(1), SpotId.create(1))
        g.place_entity(EntityId.create(2), SpotId.create(2))
        svc = SoundPropagationService()
        c = svc.clarity_for_listener(
            EntityId.create(1),
            EntityId.create(2),
            SoundVolumeEnum.NORMAL,
            g,
        )
        assert c == SoundClarityEnum.MUFFLED

    def test_recipient_carries_first_hop_connection_name_for_neighbor(self) -> None:
        """1 hop 先 listener には到来した接続の名前が乗る (Issue #269 方向情報)。"""
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(_conn(1, 1, 2, perm=0.5, name="閲覧室の扉"))
        g.place_entity(EntityId.create(1), SpotId.create(1))
        g.place_entity(EntityId.create(2), SpotId.create(2))
        svc = SoundPropagationService()
        rec = svc.resolve_recipients(EntityId.create(1), SoundVolumeEnum.NORMAL, g)
        listener = next(r for r in rec if r.entity_id == EntityId.create(2))
        assert listener.source_connection_name == "閲覧室の扉"
        assert listener.source_adjacent_spot_id == SpotId.create(1)

    def test_speaker_self_has_no_source_direction(self) -> None:
        """話者自身は方向情報を持たない (同 spot)。"""
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.place_entity(EntityId.create(1), SpotId.create(1))
        svc = SoundPropagationService()
        rec = svc.resolve_recipients(EntityId.create(1), SoundVolumeEnum.NORMAL, g)
        speaker = next(r for r in rec if r.entity_id == EntityId.create(1))
        assert speaker.source_connection_name is None
        assert speaker.source_adjacent_spot_id is None

    def test_two_hop_listener_uses_last_hop_connection(self) -> None:
        """2 hop 先の listener には「自分のスポットに音が入った最後の接続」が乗る。"""
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        for i in (1, 2, 3):
            g.add_spot(_node(i))
        g.add_connection(_conn(1, 1, 2, perm=1.0, name="図書室の扉"))
        g.add_connection(_conn(2, 2, 3, perm=1.0, name="書架の入口"))
        g.place_entity(EntityId.create(1), SpotId.create(1))
        g.place_entity(EntityId.create(3), SpotId.create(3))
        svc = SoundPropagationService()
        # SHOUT = 2 hop
        rec = svc.resolve_recipients(EntityId.create(1), SoundVolumeEnum.SHOUT, g)
        listener = next(r for r in rec if r.entity_id == EntityId.create(3))
        # 「書架の入口」が listener=spot3 への最後の接続
        assert listener.source_connection_name == "書架の入口"
        assert listener.source_adjacent_spot_id == SpotId.create(2)

    def test_outcome_for_listener_returns_recipient_or_none(self) -> None:
        """outcome_for_listener は SoundRecipient を返し、届かなければ None。"""
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        g.add_connection(_conn(1, 1, 2, perm=0.5, name="扉"))
        g.place_entity(EntityId.create(1), SpotId.create(1))
        g.place_entity(EntityId.create(2), SpotId.create(2))
        svc = SoundPropagationService()
        out = svc.outcome_for_listener(
            EntityId.create(1),
            EntityId.create(2),
            SoundVolumeEnum.NORMAL,
            g,
        )
        assert out is not None
        assert out.clarity == SoundClarityEnum.MUFFLED
        assert out.source_connection_name == "扉"
        # 届かないケース: WHISPER は 0 hop なので隣接の listener には届かない
        out2 = svc.outcome_for_listener(
            EntityId.create(1),
            EntityId.create(2),
            SoundVolumeEnum.WHISPER,
            g,
        )
        assert out2 is None

    def test_iter_outgoing_used_for_sound(self) -> None:
        """通行不可でも音は sound_permeability で届く想定"""
        g = SpotGraphAggregate.empty(SpotGraphId.create(1))
        g.add_spot(_node(1))
        g.add_spot(_node(2))
        from ai_rpg_world.domain.world_graph.enum.passage_kind import DoorStateEnum
        closed = SpotConnection(
            connection_id=ConnectionId.create(1),
            from_spot_id=SpotId.create(1),
            to_spot_id=SpotId.create(2),
            name="door",
            description="",
            travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.door(DoorStateEnum.LOCKED, sound_permeability=0.6),
        )
        g.add_connection(closed)
        g.place_entity(EntityId.create(1), SpotId.create(1))
        g.place_entity(EntityId.create(2), SpotId.create(2))
        svc = SoundPropagationService()
        rec = svc.resolve_recipients(EntityId.create(1), SoundVolumeEnum.NORMAL, g)
        assert any(r.entity_id == EntityId.create(2) for r in rec)
