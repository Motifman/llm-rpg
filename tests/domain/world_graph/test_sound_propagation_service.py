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


def _conn(cid: int, a: int, b: int, *, perm: float = 1.0) -> SpotConnection:
    return SpotConnection(
        connection_id=ConnectionId.create(cid),
        from_spot_id=SpotId.create(a),
        to_spot_id=SpotId.create(b),
        name="c",
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
