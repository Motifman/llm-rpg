from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, FrozenSet, List, Optional, Tuple

from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.sound_intensity_enum import (
    SoundIntensityEnum,
)
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    ConnectionCreatedEvent,
    ConnectionDestroyedEvent,
    ConnectionStateChangedEvent,
    EntityEnteredSpotEvent,
    SpotSoundHeardEvent,
    EntityLeftSpotEvent,
    MonsterAppearedAtSpotEvent,
    MonsterLeftSpotEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ConnectionNotPassableException,
    DuplicateConnectionIdException,
    DuplicateSpotException,
    EntityNotAtSpotException,
    EntityNotInGraphException,
    MonsterNotInGraphException,
    MonsterPresenceInvariantException,
    SpotNotInGraphException,
    SpotPresenceInvariantException,
    UnknownConnectionException,
)
from ai_rpg_world.domain.world_graph.value_object.monster_spot_presence import (
    MonsterSpotPresence,
)
from ai_rpg_world.domain.world_graph.service.spot_graph_navigation_service import SpotGraphNavigationService
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_presence import SpotPresence


@dataclass(frozen=True)
class SpotGraphConnectionRecord:
    """永続化・スナップショット向けの接続レコード。"""

    connection: SpotConnection
    reverse_connection_id: Optional[ConnectionId] = None

    @property
    def is_bidirectional(self) -> bool:
        return self.reverse_connection_id is not None


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
        reverse_connections: Optional[Dict[ConnectionId, ConnectionId]] = None,
        monster_presences: Optional[Dict[SpotId, MonsterSpotPresence]] = None,
        monster_spot: Optional[Dict[MonsterId, SpotId]] = None,
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
        self._reverse_connections: Dict[ConnectionId, ConnectionId] = dict(reverse_connections or {})
        self._monster_presences: Dict[SpotId, MonsterSpotPresence] = dict(monster_presences or {})
        self._monster_spot: Dict[MonsterId, SpotId] = dict(monster_spot or {})
        self._navigation = SpotGraphNavigationService()
        self._validate_monster_presence_consistency()

    def _validate_monster_presence_consistency(self) -> None:
        """`_monster_spot` と `_monster_presences` の二重インデックスが
        コンストラクタ復元時に整合していることを保証する。

        永続化レイヤから片方だけ欠けた状態でロードされると `unplace_monster`
        が `_monster_spot.pop` だけ成功させてからスポット側 presence の
        `remove` で例外を投げ、`_monster_spot` のみ消えるという食い違いが
        発生し得る。ここで早期に弾けば、運用パスはどちらの辞書を信じても
        同じ結果になる。
        """
        for monster_id, spot_id in self._monster_spot.items():
            pres = self._monster_presences.get(spot_id)
            if pres is None or monster_id not in pres.present_monster_ids:
                raise MonsterPresenceInvariantException(
                    f"Inconsistent monster presence on restore: {monster_id} "
                    f"mapped to {spot_id} but not present in spot presence set"
                )
        for spot_id, pres in self._monster_presences.items():
            for monster_id in pres.present_monster_ids:
                mapped = self._monster_spot.get(monster_id)
                if mapped != spot_id:
                    raise MonsterPresenceInvariantException(
                        f"Inconsistent monster presence on restore: {monster_id} "
                        f"present at {spot_id} but mapping points to {mapped}"
                    )

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
            if c.passage.traversable:
                out.append(c.to_spot_id)
        return out

    def find_first_passable_connection_between(
        self, from_spot_id: SpotId, to_spot_id: SpotId
    ) -> Optional[SpotConnection]:
        """from から出る有向エッジのうち、先が to かつ通行可能な最初の接続。無ければ None。"""
        for cid in self._outgoing.get(from_spot_id, []):
            c = self._connections_by_id[cid]
            if c.to_spot_id == to_spot_id and c.passage.traversable:
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
            self._reverse_connections[conn.connection_id] = reverse_connection_id
            self._reverse_connections[reverse_connection_id] = conn.connection_id

    def _register_edge(self, conn: SpotConnection, *, emit_event: bool = False) -> None:
        self._connections_by_id[conn.connection_id] = conn
        self._outgoing.setdefault(conn.from_spot_id, []).append(conn.connection_id)
        if emit_event:
            self.add_event(
                ConnectionCreatedEvent.create(
                    aggregate_id=self._graph_id,
                    aggregate_type="SpotGraphAggregate",
                    connection_id=conn.connection_id,
                    from_spot_id=conn.from_spot_id,
                    to_spot_id=conn.to_spot_id,
                )
            )

    def add_connection_dynamic(
        self,
        conn: SpotConnection,
        reverse_connection_id: Optional[ConnectionId] = None,
    ) -> None:
        """ゲーム中の動的接続追加。ConnectionCreatedEvent を発行する。"""
        if conn.connection_id in self._connections_by_id:
            raise DuplicateConnectionIdException(f"Connection ID already used: {conn.connection_id}")
        if conn.from_spot_id not in self._spots or conn.to_spot_id not in self._spots:
            raise SpotNotInGraphException("Both endpoints must be registered spots")
        self._register_edge(conn, emit_event=True)
        if conn.is_bidirectional:
            if reverse_connection_id is None:
                raise ValueError("reverse_connection_id is required when is_bidirectional is True")
            if reverse_connection_id in self._connections_by_id:
                raise DuplicateConnectionIdException(f"Reverse connection ID already used: {reverse_connection_id}")
            from dataclasses import replace as _replace
            rev = _replace(
                conn,
                connection_id=reverse_connection_id,
                from_spot_id=conn.to_spot_id,
                to_spot_id=conn.from_spot_id,
            )
            self._register_edge(rev, emit_event=True)
            self._reverse_connections[conn.connection_id] = reverse_connection_id
            self._reverse_connections[reverse_connection_id] = conn.connection_id

    def max_connection_id_value(self) -> int:
        """グラフ内の既存接続IDの最大値を返す。接続がなければ0。"""
        if not self._connections_by_id:
            return 0
        return max(cid.value for cid in self._connections_by_id)

    def get_connection(self, connection_id: ConnectionId) -> SpotConnection:
        if connection_id not in self._connections_by_id:
            raise UnknownConnectionException(f"Unknown connection: {connection_id}")
        return self._connections_by_id[connection_id]

    def place_entity(self, entity_id: EntityId, spot_id: SpotId) -> None:
        """初回配置。from_spot_id=None の EntityEnteredSpotEvent を発行。

        Phase 5: spot の `sound_intensity` が SILENT より大きい場合、
        `SpotSoundHeardEvent` も発行して受動的な環境音観測を agent に届ける。
        """
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
        self._maybe_emit_spot_sound_heard(entity_id, spot_id)

    def unplace_entity(self, entity_id: EntityId) -> None:
        """エンティティをグラフから取り除く。

        テストや管理用途のための逆操作。move_entity と違ってアイテム / フラグ等の
        通行条件チェックを行わず、イベントも発行しない。本番ロジックでは
        move_entity を使うこと。
        """
        if entity_id not in self._entity_spot:
            raise EntityNotInGraphException(f"Entity not placed: {entity_id}")
        spot_id = self._entity_spot.pop(entity_id)
        pres = self._presences.get(spot_id, SpotPresence.empty(spot_id))
        self._presences[spot_id] = pres.remove(entity_id)

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
        # Phase 5: 移動先の spot に環境音があれば観測 event を発火
        self._maybe_emit_spot_sound_heard(entity_id, to_spot)

    def _maybe_emit_spot_sound_heard(
        self, entity_id: EntityId, spot_id: SpotId,
    ) -> None:
        """spot の sound_intensity が SILENT 以外なら SpotSoundHeardEvent を発火。

        Phase 5: 入場 / 移動時の受動的な環境音観測。`source_spot_id == spot_id`
        (自分が居る spot から聞こえる音) として発火する。PR-2 の
        `emit_listen_carefully` も同じ helper を共有することで、減衰なし発火
        の挙動を一箇所に集約する。
        """
        self._emit_sound_heard(entity_id, spot_id, spot_id)

    def emit_listen_carefully(self, entity_id: EntityId) -> None:
        """「耳を澄ます」ツール (Phase 5 PR-2) の event 発火。

        entity が居る spot および全隣接 spot (1 hop) の sound_intensity を
        観測する `SpotSoundHeardEvent` を `add_event` する。

        伝搬モデル:
        - 自 spot: `SoundIntensityEnum` をそのまま (減衰なし)
        - 隣接 spot: `attenuate(1)` で 1 段階下げる
        - 減衰結果が SILENT になった spot は event 発火しない (聞こえない)
        - 隣接 spot の重複 (複数 connection で同 spot に繋がる場合) は dedup

        通行可否は無視 (壁越し / 閉じた扉越しでも音は届く)。接続種別による
        減衰補正は将来 PR のスコープ。

        Raises:
            EntityNotInGraphException: entity が graph 上に配置されていない
        """
        current_spot = self.get_entity_spot(entity_id)
        self._emit_sound_heard(entity_id, current_spot, current_spot)

        seen_adjacent: set = set()
        for conn in self.iter_outgoing_connections_from(current_spot):
            adj_spot = conn.to_spot_id
            if adj_spot == current_spot or adj_spot in seen_adjacent:
                continue
            seen_adjacent.add(adj_spot)
            self._emit_sound_heard(
                entity_id,
                listener_spot_id=current_spot,
                source_spot_id=adj_spot,
                attenuation_hops=1,
            )

    def _emit_sound_heard(
        self,
        entity_id: EntityId,
        listener_spot_id: SpotId,
        source_spot_id: SpotId,
        attenuation_hops: int = 0,
    ) -> None:
        """source_spot の sound_intensity を attenuate して event を発火する。

        - 音源 spot 自体が無い / atmosphere 無し → 何もしない
        - 減衰後 SILENT → 何もしない (聞こえないので observation 不要)
        """
        node = self._spots.get(source_spot_id)
        if node is None or node.atmosphere is None:
            return
        intensity = node.atmosphere.sound_intensity
        if attenuation_hops > 0:
            intensity = intensity.attenuate(attenuation_hops)
        if intensity == SoundIntensityEnum.SILENT:
            return
        self.add_event(
            SpotSoundHeardEvent.create(
                aggregate_id=self._graph_id,
                aggregate_type="SpotGraphAggregate",
                entity_id=entity_id,
                spot_id=listener_spot_id,
                source_spot_id=source_spot_id,
                intensity=intensity.value,
                ambient_description=node.atmosphere.sound_ambient,
            )
        )

    def set_connection_passage(
        self, connection_id: ConnectionId, new_passage: Passage
    ) -> None:
        """接続の Passage を新しい値に置換する。

        通行可否が変化した場合は ConnectionStateChangedEvent も発火する。
        """
        conn = self.get_connection(connection_id)
        prev_traversable = conn.passage.traversable
        new_conn = replace(conn, passage=new_passage)
        self._connections_by_id[connection_id] = new_conn
        if new_conn.passage.traversable != prev_traversable:
            self.add_event(
                ConnectionStateChangedEvent.create(
                    aggregate_id=self._graph_id,
                    aggregate_type="SpotGraphAggregate",
                    connection_id=connection_id,
                    from_spot_id=conn.from_spot_id,
                    to_spot_id=conn.to_spot_id,
                    traversable=new_conn.passage.traversable,
                )
            )

    def set_connection_passage_state(
        self,
        connection_id: ConnectionId,
        new_state: str,
        *,
        traversable_override: Optional[bool] = None,
        sound_permeability_override: Optional[float] = None,
    ) -> None:
        """既存の Passage と同じ kind を維持したまま状態だけ遷移させる。"""
        conn = self.get_connection(connection_id)
        new_passage = conn.passage.with_state(
            new_state,
            traversable=traversable_override,
            sound_permeability=sound_permeability_override,
        )
        self.set_connection_passage(connection_id, new_passage)

    def remove_connection(self, connection_id: ConnectionId) -> None:
        """接続をグラフから完全に削除する。双方向の場合は逆方向も削除。"""
        conn = self.get_connection(connection_id)
        out_list = self._outgoing.get(conn.from_spot_id)
        if out_list is not None and connection_id in out_list:
            out_list.remove(connection_id)
        del self._connections_by_id[connection_id]
        rev_id = self._reverse_connections.pop(connection_id, None)
        if rev_id is not None:
            rev_out = self._outgoing.get(conn.to_spot_id)
            if rev_out is not None and rev_id in rev_out:
                rev_out.remove(rev_id)
            self._connections_by_id.pop(rev_id, None)
            self._reverse_connections.pop(rev_id, None)
        self.add_event(
            ConnectionDestroyedEvent.create(
                aggregate_id=self._graph_id,
                aggregate_type="SpotGraphAggregate",
                connection_id=connection_id,
                from_spot_id=conn.from_spot_id,
                to_spot_id=conn.to_spot_id,
            )
        )

    def get_entity_spot(self, entity_id: EntityId) -> SpotId:
        if entity_id not in self._entity_spot:
            raise EntityNotInGraphException(f"Entity not placed: {entity_id}")
        return self._entity_spot[entity_id]

    def presence_at(self, spot_id: SpotId) -> SpotPresence:
        return self._presences.get(spot_id, SpotPresence.empty(spot_id))

    def iter_spot_nodes(self) -> Tuple[SpotNode, ...]:
        """永続化・スナップショット用に登録済みスポットノードを列挙する。"""
        return tuple(self._spots.values())

    def all_connections(self) -> Tuple[SpotConnection, ...]:
        """永続化用に接続（双方向は二重エッジのまま）を列挙する。"""
        return tuple(self._connections_by_id.values())

    def iter_connection_records(self) -> Tuple[SpotGraphConnectionRecord, ...]:
        """双方向ペアを明示した接続レコードを返す。"""
        records: List[SpotGraphConnectionRecord] = []
        handled: set[ConnectionId] = set()
        for conn in sorted(
            self._connections_by_id.values(),
            key=lambda item: int(item.connection_id.value),
        ):
            if conn.connection_id in handled:
                continue
            reverse_id = self._reverse_connections.get(conn.connection_id)
            if reverse_id is None:
                records.append(SpotGraphConnectionRecord(connection=conn))
                handled.add(conn.connection_id)
                continue

            reverse_conn = self._connections_by_id.get(reverse_id)
            if reverse_conn is None:
                raise SpotPresenceInvariantException(
                    f"Reverse connection missing for {conn.connection_id}: {reverse_id}"
                )
            if self._reverse_connections.get(reverse_id) != conn.connection_id:
                raise SpotPresenceInvariantException(
                    f"Reverse connection pair is inconsistent: {conn.connection_id} <-> {reverse_id}"
                )

            forward = conn
            backward = reverse_conn
            if int(forward.connection_id.value) > int(backward.connection_id.value):
                forward, backward = backward, forward
            records.append(
                SpotGraphConnectionRecord(
                    connection=forward,
                    reverse_connection_id=backward.connection_id,
                )
            )
            handled.add(forward.connection_id)
            handled.add(backward.connection_id)
        return tuple(records)

    def entity_spot_mapping(self) -> Dict[EntityId, SpotId]:
        """エンティティの所在スポット（永続化用）。"""
        return dict(self._entity_spot)

    # ------------------------------------------------------------------
    # Monster presence (静的に居るだけのモンスター個体配置)
    #
    # ステップ1ではスポット間移動も行動も持たない。`place_monster` で
    # スポットに置き、`unplace_monster` でグラフから取り除くだけ。プレ
    # イヤーの SpotPresence と独立した辞書で管理し、観測導線・生態系
    # tick・戦闘 PR で個別に発展させる。
    # ------------------------------------------------------------------

    def place_monster(self, monster_id: MonsterId, spot_id: SpotId) -> None:
        """モンスター個体をスポットに出現させる。

        既に配置済みの monster_id を再配置しようとした場合は不変条件
        違反として `MonsterPresenceInvariantException` を投げる。

        Phase 5: `place_entity` (player) と異なり、monster 出現では
        `SpotSoundHeardEvent` を発火しない。SpotSoundHeardEvent は LLM
        プレイヤーに観測として届けるためのものであり、monster は観測
        パイプラインの recipient にならない設計のため。
        """
        if spot_id not in self._spots:
            raise SpotNotInGraphException(f"Unknown spot: {spot_id}")
        if monster_id in self._monster_spot:
            raise MonsterPresenceInvariantException(
                f"Monster already placed: {monster_id}"
            )
        self._monster_spot[monster_id] = spot_id
        pres = self._monster_presences.get(spot_id, MonsterSpotPresence.empty(spot_id))
        self._monster_presences[spot_id] = pres.add(monster_id)
        self.add_event(
            MonsterAppearedAtSpotEvent.create(
                aggregate_id=self._graph_id,
                aggregate_type="SpotGraphAggregate",
                monster_id=monster_id,
                spot_id=spot_id,
            )
        )

    def unplace_monster(self, monster_id: MonsterId) -> None:
        """モンスター個体をグラフから取り除く（despawn / 死亡 / 撤去）。

        `_monster_spot` と `_monster_presences` の両方を必ず一緒に更新する。
        除去後に空になったスポットは `_monster_presences` からキー自体を
        消し、永続化時に空レコードが残らないようにする。
        """
        if monster_id not in self._monster_spot:
            raise MonsterNotInGraphException(f"Monster not placed: {monster_id}")
        spot_id = self._monster_spot[monster_id]
        pres = self._monster_presences.get(spot_id, MonsterSpotPresence.empty(spot_id))
        new_pres = pres.remove(monster_id)
        if new_pres.count() == 0:
            self._monster_presences.pop(spot_id, None)
        else:
            self._monster_presences[spot_id] = new_pres
        del self._monster_spot[monster_id]
        self.add_event(
            MonsterLeftSpotEvent.create(
                aggregate_id=self._graph_id,
                aggregate_type="SpotGraphAggregate",
                monster_id=monster_id,
                spot_id=spot_id,
            )
        )

    def can_traverse_connection(
        self,
        connection_id: ConnectionId,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
    ) -> bool:
        """指定接続が `Passage.traversable=True` かつ `passage_conditions` を
        全て満たすかを返す。public 側から `_navigation.can_pass` を直接触らずに
        合否だけ問い合わせるためのヘルパー。

        モンスター徘徊の事前フィルタや、UI 側で "このプレイヤーがそこを通れるか"
        を表示する用途に使う。
        """
        conn = self.get_connection(connection_id)
        ok, _ = self._navigation.can_pass(conn, owned_item_spec_ids, world_flags)
        return ok

    def move_monster(
        self,
        monster_id: MonsterId,
        connection_id: ConnectionId,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
    ) -> None:
        """モンスター個体を接続経由で隣接スポットへ移動する。

        プレイヤーの `move_entity` と対称構造。`Passage` の通行条件
        (`SpotGraphNavigationService.can_pass`) を尊重するため、鍵が要る
        扉やフラグ付き通路はモンスターも通れない。

        emit する event は `MonsterLeftSpotEvent` → `MonsterAppearedAtSpotEvent`
        の対。受信者解決はそれぞれ「元 spot 全員」「先 spot 全員」となるため、
        観測パイプラインを書き換えずに移動を表現できる（PR #124 の docstring
        で示唆していた選択肢のうち「Left → Appeared を対で発火」を採用）。

        ALIVE/DEAD は集約レベルで管理しないため、`MonsterAggregate` の状態は
        呼び出し側で確認する責任がある（ALIVE 以外を移動させたいケースは
        無いはずだが、本メソッドはそのチェックを行わない）。

        Phase 5: `move_entity` (player) と異なり、monster 移動では
        `SpotSoundHeardEvent` を発火しない (player 観測パイプライン専用)。
        """
        if monster_id not in self._monster_spot:
            raise MonsterNotInGraphException(f"Monster not placed: {monster_id}")
        conn = self.get_connection(connection_id)
        from_spot = self._monster_spot[monster_id]
        if from_spot != conn.from_spot_id:
            raise SpotPresenceInvariantException(
                f"Monster {monster_id} is at {from_spot}, "
                f"not at connection origin {conn.from_spot_id}"
            )
        ok, reason = self._navigation.can_pass(conn, owned_item_spec_ids, world_flags)
        if not ok:
            raise ConnectionNotPassableException(reason or "Cannot pass")

        to_spot = conn.to_spot_id

        old_pres = self._monster_presences.get(
            from_spot, MonsterSpotPresence.empty(from_spot)
        )
        new_old_pres = old_pres.remove(monster_id)
        if new_old_pres.count() == 0:
            self._monster_presences.pop(from_spot, None)
        else:
            self._monster_presences[from_spot] = new_old_pres

        dest_pres = self._monster_presences.get(
            to_spot, MonsterSpotPresence.empty(to_spot)
        )
        self._monster_presences[to_spot] = dest_pres.add(monster_id)
        self._monster_spot[monster_id] = to_spot

        self.add_event(
            MonsterLeftSpotEvent.create(
                aggregate_id=self._graph_id,
                aggregate_type="SpotGraphAggregate",
                monster_id=monster_id,
                spot_id=from_spot,
            )
        )
        self.add_event(
            MonsterAppearedAtSpotEvent.create(
                aggregate_id=self._graph_id,
                aggregate_type="SpotGraphAggregate",
                monster_id=monster_id,
                spot_id=to_spot,
            )
        )

    def get_monster_spot(self, monster_id: MonsterId) -> SpotId:
        if monster_id not in self._monster_spot:
            raise MonsterNotInGraphException(f"Monster not placed: {monster_id}")
        return self._monster_spot[monster_id]

    def is_monster_present(self, monster_id: MonsterId) -> bool:
        return monster_id in self._monster_spot

    def monster_presence_at(self, spot_id: SpotId) -> MonsterSpotPresence:
        return self._monster_presences.get(spot_id, MonsterSpotPresence.empty(spot_id))

    def monster_spot_mapping(self) -> Dict[MonsterId, SpotId]:
        """モンスターの所在スポット（永続化用）。"""
        return dict(self._monster_spot)

    def monster_presences_mapping(self) -> Dict[SpotId, MonsterSpotPresence]:
        """スポット → モンスター在席集合（永続化用の防御的コピー）。

        コンストラクタ引数 `monster_presences` と対称になる入出力。Sqlite
        repository などが集約を復元する際は本メソッドの返値と
        `monster_spot_mapping()` の両方を保存し、両方を合わせて読み戻す。
        """
        return dict(self._monster_presences)
