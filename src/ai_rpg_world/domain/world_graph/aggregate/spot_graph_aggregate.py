from __future__ import annotations

from dataclasses import replace
from typing import Dict, FrozenSet, List, Optional

from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    ConnectionStateChangedEvent,
    EntityEnteredSpotEvent,
    EntityLeftSpotEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ConnectionNotPassableException,
    DuplicateConnectionIdException,
    DuplicateSpotException,
    EntityNotAtSpotException,
    EntityNotInGraphException,
    SpotNotInGraphException,
    SpotPresenceInvariantException,
    UnknownConnectionException,
)
from ai_rpg_world.domain.world_graph.service.spot_graph_navigation_service import SpotGraphNavigationService
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_presence import SpotPresence


class SpotGraphAggregate(AggregateRoot):
    """スポットの接続グラフと在席状態を管理する集約"""

    def __init__(
        self,
        graph_id: SpotGraphId,
        spots: Optional[Dict[SpotId, SpotNode]] = None,
        connections_by_id: Optional[Dict[ConnectionId, SpotConnection]] = None,
        outgoing: Optional[Dict[SpotId, List[ConnectionId]]] = None,
        presences: Optional[Dict[SpotId, SpotPresence]] = None,
        entity_spot: Optional[Dict[EntityId, SpotId]] = None,
    ) -> None:
        super().__init__()
        self._graph_id = graph_id
        self._spots: Dict[SpotId, SpotNode] = dict(spots or {})
        self._connections_by_id: Dict[ConnectionId, SpotConnection] = dict(connections_by_id or {})
        self._outgoing: Dict[SpotId, List[ConnectionId]] = {
            k: list(v) for k, v in (outgoing or {}).items()
        }
        self._presences: Dict[SpotId, SpotPresence] = dict(presences or {})
        self._entity_spot: Dict[EntityId, SpotId] = dict(entity_spot or {})
        self._navigation = SpotGraphNavigationService()

    @property
    def graph_id(self) -> SpotGraphId:
        return self._graph_id

    @classmethod
    def empty(cls, graph_id: SpotGraphId) -> SpotGraphAggregate:
        return cls(graph_id=graph_id)

    def contains_spot(self, spot_id: SpotId) -> bool:
        return spot_id in self._spots

    def get_spot(self, spot_id: SpotId) -> SpotNode:
        if spot_id not in self._spots:
            raise SpotNotInGraphException(f"Spot not in graph: {spot_id}")
        return self._spots[spot_id]

    def neighbor_spot_ids_for_routing(self, spot_id: SpotId) -> List[SpotId]:
        """通行可能な出方向エッジの先スポット（経路探索用）"""
        out: List[SpotId] = []
        for cid in self._outgoing.get(spot_id, []):
            c = self._connections_by_id[cid]
            if c.is_passable:
                out.append(c.to_spot_id)
        return out

    def find_first_passable_connection_between(
        self, from_spot_id: SpotId, to_spot_id: SpotId
    ) -> Optional[SpotConnection]:
        """from から出る有向エッジのうち、先が to かつ通行可能な最初の接続。無ければ None。"""
        for cid in self._outgoing.get(from_spot_id, []):
            c = self._connections_by_id[cid]
            if c.to_spot_id == to_spot_id and c.is_passable:
                return c
        return None

    def iter_outgoing_connections_from(self, spot_id: SpotId) -> List[SpotConnection]:
        """出方向の全接続（通行可否に依らない。音の伝播経路用）。"""
        return [self._connections_by_id[cid] for cid in self._outgoing.get(spot_id, [])]

    def add_spot(self, node: SpotNode) -> None:
        if node.spot_id in self._spots:
            raise DuplicateSpotException(f"Spot already registered: {node.spot_id}")
        self._spots[node.spot_id] = node
        if node.spot_id not in self._presences:
            self._presences[node.spot_id] = SpotPresence.empty(node.spot_id)

    def add_connection(
        self,
        conn: SpotConnection,
        reverse_connection_id: Optional[ConnectionId] = None,
    ) -> None:
        if conn.connection_id in self._connections_by_id:
            raise DuplicateConnectionIdException(f"Connection ID already used: {conn.connection_id}")
        if conn.from_spot_id not in self._spots or conn.to_spot_id not in self._spots:
            raise SpotNotInGraphException("Both endpoints must be registered spots")
        self._register_edge(conn)
        if conn.is_bidirectional:
            if reverse_connection_id is None:
                raise ValueError(
                    "reverse_connection_id is required when is_bidirectional is True"
                )
            if reverse_connection_id in self._connections_by_id:
                raise DuplicateConnectionIdException(
                    f"Reverse connection ID already used: {reverse_connection_id}"
                )
            rev = replace(
                conn,
                connection_id=reverse_connection_id,
                from_spot_id=conn.to_spot_id,
                to_spot_id=conn.from_spot_id,
            )
            self._register_edge(rev)

    def _register_edge(self, conn: SpotConnection) -> None:
        self._connections_by_id[conn.connection_id] = conn
        self._outgoing.setdefault(conn.from_spot_id, []).append(conn.connection_id)

    def get_connection(self, connection_id: ConnectionId) -> SpotConnection:
        if connection_id not in self._connections_by_id:
            raise UnknownConnectionException(f"Unknown connection: {connection_id}")
        return self._connections_by_id[connection_id]

    def place_entity(self, entity_id: EntityId, spot_id: SpotId) -> None:
        """初回配置。from_spot_id=None の EntityEnteredSpotEvent を発行。"""
        if entity_id in self._entity_spot:
            raise SpotPresenceInvariantException(f"Entity already placed: {entity_id}")
        if spot_id not in self._spots:
            raise SpotNotInGraphException(f"Unknown spot: {spot_id}")
        self._entity_spot[entity_id] = spot_id
        pres = self._presences.get(spot_id, SpotPresence.empty(spot_id))
        self._presences[spot_id] = pres.add(entity_id)
        ev = EntityEnteredSpotEvent.create(
            aggregate_id=self._graph_id,
            aggregate_type="SpotGraphAggregate",
            entity_id=entity_id,
            spot_id=spot_id,
            from_spot_id=None,
        )
        self.add_event(ev)

    def move_entity(
        self,
        entity_id: EntityId,
        connection_id: ConnectionId,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
    ) -> None:
        """接続に沿って移動。Left → Entered の順でイベントを発行。"""
        if entity_id not in self._entity_spot:
            raise EntityNotInGraphException(f"Entity not placed: {entity_id}")
        conn = self.get_connection(connection_id)
        from_spot = self._entity_spot[entity_id]
        if from_spot != conn.from_spot_id:
            raise EntityNotAtSpotException(
                f"Entity {entity_id} is at {from_spot}, not at connection origin {conn.from_spot_id}"
            )
        ok, reason = self._navigation.can_pass(conn, owned_item_spec_ids, world_flags)
        if not ok:
            raise ConnectionNotPassableException(reason or "Cannot pass")

        to_spot = conn.to_spot_id
        old_pres = self._presences.get(from_spot, SpotPresence.empty(from_spot))
        new_pres = old_pres.remove(entity_id)
        self._presences[from_spot] = new_pres

        dest_pres = self._presences.get(to_spot, SpotPresence.empty(to_spot))
        self._presences[to_spot] = dest_pres.add(entity_id)
        self._entity_spot[entity_id] = to_spot

        self.add_event(
            EntityLeftSpotEvent.create(
                aggregate_id=self._graph_id,
                aggregate_type="SpotGraphAggregate",
                entity_id=entity_id,
                spot_id=from_spot,
                to_spot_id=to_spot,
            )
        )
        self.add_event(
            EntityEnteredSpotEvent.create(
                aggregate_id=self._graph_id,
                aggregate_type="SpotGraphAggregate",
                entity_id=entity_id,
                spot_id=to_spot,
                from_spot_id=from_spot,
            )
        )

    def set_connection_passable(self, connection_id: ConnectionId, passable: bool) -> None:
        conn = self.get_connection(connection_id)
        if conn.is_passable == passable:
            return
        new_conn = replace(conn, is_passable=passable)
        self._connections_by_id[connection_id] = new_conn
        self.add_event(
            ConnectionStateChangedEvent.create(
                aggregate_id=self._graph_id,
                aggregate_type="SpotGraphAggregate",
                connection_id=connection_id,
                from_spot_id=conn.from_spot_id,
                to_spot_id=conn.to_spot_id,
                is_passable=passable,
            )
        )

    def get_entity_spot(self, entity_id: EntityId) -> SpotId:
        if entity_id not in self._entity_spot:
            raise EntityNotInGraphException(f"Entity not placed: {entity_id}")
        return self._entity_spot[entity_id]

    def presence_at(self, spot_id: SpotId) -> SpotPresence:
        return self._presences.get(spot_id, SpotPresence.empty(spot_id))
