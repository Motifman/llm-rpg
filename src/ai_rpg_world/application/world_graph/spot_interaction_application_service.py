from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from ai_rpg_world.application.common.exceptions import ApplicationException
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
    remove_one_item_of_spec_from_inventory,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import ISpotGraphRepository
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import ISpotInteriorRepository
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import SpotInteractionService
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotObjectInteractedEvent,
    SpotObjectInteractionFailedEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


@dataclass(frozen=True)
class SpotInteractionResultDto:
    messages: Tuple[str, ...]


class SpotInteractionApplicationService:
    """スポット内オブジェクト操作（ドメインサービス + 永続化・フラグ・アイテム・接続状態）。"""

    def __init__(
        self,
        spot_graph_repository: ISpotGraphRepository,
        spot_interior_repository: ISpotInteriorRepository,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
        item_spec_repository: ItemSpecRepository,
        world_flag_state: MutableWorldFlagState,
        spot_interaction_service: SpotInteractionService | None = None,
        player_status_repository: PlayerStatusRepository | None = None,
        event_publisher: Any | None = None,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._spot_interior_repository = spot_interior_repository
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        self._item_spec_repository = item_spec_repository
        self._world_flag_state = world_flag_state
        self._interaction = spot_interaction_service or SpotInteractionService()
        self._player_status_repository = player_status_repository
        self._event_publisher = event_publisher

    def execute_interaction(
        self,
        player_id: PlayerId,
        object_id: SpotObjectId,
        action_name: str,
        *,
        interaction_parameters: Optional[Dict[str, Any]] = None,
        current_tick: Optional[WorldTick] = None,
        acting_item_instance_id: Optional["ItemInstanceId"] = None,
        target_item_instance_id: Optional["ItemInstanceId"] = None,
    ) -> SpotInteractionResultDto:
        graph = self._spot_graph_repository.find_graph()
        entity_id = EntityId.create(int(player_id))
        spot_id = graph.get_entity_spot(entity_id)

        interior = self._spot_interior_repository.find_by_spot_id(spot_id)
        if interior is None:
            raise ApplicationException(
                f"スポット内部データがありません: {spot_id}",
                spot_id=int(spot_id),
            )

        inv = self._player_inventory_repository.find_by_id(player_id)
        if inv is None:
            raise ApplicationException(
                f"インベントリが見つかりません: {player_id}",
                player_id=int(player_id),
            )

        owned = collect_owned_item_spec_ids_from_inventory(inv, self._item_repository)
        owned_counts = count_owned_item_instances_by_spec(inv, self._item_repository)
        world_flags = self._world_flag_state.as_frozen_set()

        # Phase 4-A: 「使う対象 item instance」の解決。
        # acting_item_instance_id が渡された場合のみ aggregate をロードし、
        # interaction の effect / precondition から in-place に state を
        # 操作できるよう domain service に渡す。後で state が変わった
        # ときだけ item_repository に save する責務がここにある。
        acting_item_aggregate = None
        if acting_item_instance_id is not None:
            acting_item_aggregate = self._item_repository.find_by_id(
                acting_item_instance_id
            )
            if acting_item_aggregate is None:
                raise ApplicationException(
                    f"acting item instance が見つかりません: {acting_item_instance_id.value}",
                    player_id=int(player_id),
                )

        # Phase 4-B: 「使われる側 (target) item instance」の解決。
        # 二者間の相互作用 (修理キットを錆びた剣に使う等) で、acting と
        # 並列に target_item_instance_id を読み込み、domain service に渡す。
        # state が変わったときだけ save する責務もここに置く。
        target_item_aggregate = None
        if target_item_instance_id is not None:
            if (
                acting_item_instance_id is not None
                and acting_item_instance_id == target_item_instance_id
            ):
                # 同 ID を両方に渡すのは作家ミス。domain 層でも `is` 比較で
                # 同じ aggregate を弾くが、ID 等価でも別 aggregate ロードに
                # なるとガードを抜けてしまうので app 層でも値で弾く。
                raise ApplicationException(
                    "acting と target に同じ item_instance_id を渡すことはできません",
                    player_id=int(player_id),
                )
            target_item_aggregate = self._item_repository.find_by_id(
                target_item_instance_id
            )
            if target_item_aggregate is None:
                raise ApplicationException(
                    f"target item instance が見つかりません: {target_item_instance_id.value}",
                    player_id=int(player_id),
                )

        try:
            result = self._interaction.execute_interaction(
                interior,
                object_id,
                action_name,
                owned,
                world_flags,
                interaction_parameters=interaction_parameters,
                current_tick=current_tick,
                owned_item_spec_counts=owned_counts,
                acting_item_aggregate=acting_item_aggregate,
                target_item_aggregate=target_item_aggregate,
            )
        except InteractionNotAllowedException:
            # 前提条件で拒否された。InteractionDef.on_failure_observation が
            # 設定されていれば、同じスポットの他プレイヤー向け観測を出してから
            # 例外を re-raise する（アクターには tool result としてエラーが返る）。
            self._maybe_emit_failure_observation(
                interior, object_id, action_name, entity_id, spot_id, graph,
            )
            raise

        self._world_flag_state.replace_from_interaction(result.new_flags)

        new_interior = result.new_interior
        self._spot_interior_repository.save(spot_id, new_interior)

        for spec in result.passage_state_updates:
            graph.set_connection_passage_state(
                ConnectionId.create(spec.connection_id),
                spec.new_state,
                traversable_override=spec.traversable_override,
                sound_permeability_override=spec.sound_permeability_override,
            )

        if result.item_spec_ids_to_grant:
            grant_item_specs_to_inventory(
                player_id,
                tuple(result.item_spec_ids_to_grant),
                self._item_repository,
                self._item_spec_repository,
                self._player_inventory_repository,
            )

        inv2 = self._player_inventory_repository.find_by_id(player_id)
        if inv2 is not None:
            # REMOVE_ITEM 効果で消費するアイテムが見つからない場合、
            # 黙ってスキップすると「precondition は通ったのに消費されない」
            # という invariant 違反になる（Phase 2-A レビュー HIGH #3）。
            # precondition で count を確認している前提なので、ここで
            # 失敗するのは何かが致命的に壊れている状態。明示的に raise する。
            for spec_id in result.item_spec_ids_to_remove:
                removed = remove_one_item_of_spec_from_inventory(
                    inv2, spec_id, self._item_repository
                )
                if not removed:
                    raise ApplicationException(
                        "REMOVE_ITEM effect could not consume item "
                        f"(spec_id={spec_id.value}); precondition / count mismatch",
                        player_id=int(player_id),
                    )
            self._player_inventory_repository.save(inv2)

        # Phase 4-A: acting item instance の state が effect で変わった場合、
        # item_repository に save して永続化する。
        if (
            result.item_instance_state_changed
            and acting_item_aggregate is not None
        ):
            self._item_repository.save(acting_item_aggregate)

        # Phase 4-B: target item instance の state が変わった場合も同じく save。
        # acting と target は別 instance であることが domain layer のガードで
        # 保証されているので、両方が同じ tick で save されても問題ない。
        # TODO: SqliteItemRepository を本番投入する際は、acting / target の
        # 2 回の save を 1 トランザクション (Unit of Work) にまとめる必要がある。
        # 現状は in-memory のため partial failure が顕在化しないが、infra 層が
        # SQLite に切り替わると acting だけ save されて target で失敗する
        # ケースで state が壊れる。
        if (
            result.target_item_instance_state_changed
            and target_item_aggregate is not None
        ):
            self._item_repository.save(target_item_aggregate)

        for spec in result.destroy_connection_specs:
            graph.remove_connection(ConnectionId.create(spec.connection_id))

        for spec in result.create_connection_specs:
            new_cid = self._next_connection_id(graph)
            new_conn = SpotConnection(
                connection_id=new_cid,
                from_spot_id=SpotId.create(spec.from_spot_id),
                to_spot_id=SpotId.create(spec.to_spot_id),
                name=spec.connection_name,
                description=spec.description,
                travel_ticks=spec.travel_ticks,
                is_bidirectional=spec.is_bidirectional,
                passage=spec.passage,
            )
            rev_id = ConnectionId.create(new_cid.value + 1) if spec.is_bidirectional else None
            graph.add_connection_dynamic(new_conn, reverse_connection_id=rev_id)

        # 欲求回復
        if result.satisfy_need_specs and self._player_status_repository is not None:
            status = self._player_status_repository.find_by_id(player_id)
            if status is not None:
                for spec in result.satisfy_need_specs:
                    try:
                        need_type = NeedType(spec.need_type_name)
                        status.satisfy_need(need_type, spec.amount)
                    except ValueError:
                        pass  # 未知の NeedType は無視
                self._player_status_repository.save(status)

        # aggregate が貯めたイベント (ConnectionStateChanged 等) を抽出
        graph_events = list(graph.get_events())
        graph.clear_events()

        self._spot_graph_repository.save(graph)

        # SpotObjectInteractedEvent を明示的に作成して publish
        if self._event_publisher is not None:
            interacted_event = SpotObjectInteractedEvent.create(
                aggregate_id=graph.graph_id,
                aggregate_type="SpotGraphAggregate",
                entity_id=entity_id,
                spot_id=spot_id,
                object_id=object_id,
                action_name=action_name,
                result_message="；".join(result.messages) if result.messages else "",
            )
            self._event_publisher.publish_all([*graph_events, interacted_event])

        return SpotInteractionResultDto(messages=result.messages)

    @staticmethod
    def _next_connection_id(graph) -> ConnectionId:
        """グラフ内の既存接続IDの最大値+1を返す。"""
        return ConnectionId.create(graph.max_connection_id_value() + 1)

    def _maybe_emit_failure_observation(
        self,
        interior: SpotInterior,
        object_id: SpotObjectId,
        action_name: str,
        entity_id: EntityId,
        spot_id: SpotId,
        graph: SpotGraphAggregate,
    ) -> None:
        """InteractionDef.on_failure_observation が設定されていれば
        SpotObjectInteractionFailedEvent を publish する。"""
        if self._event_publisher is None:
            return
        obj = interior.get_object(object_id)
        if obj is None:
            return
        idef = next(
            (i for i in obj.interactions if i.action_name == action_name), None,
        )
        if idef is None or not idef.on_failure_observation:
            return
        failed_event = SpotObjectInteractionFailedEvent.create(
            aggregate_id=graph.graph_id,
            aggregate_type="SpotGraphAggregate",
            entity_id=entity_id,
            spot_id=spot_id,
            object_id=object_id,
            action_name=action_name,
            observation_message=idef.on_failure_observation,
        )
        self._event_publisher.publish_all([failed_event])
