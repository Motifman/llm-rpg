"""スポットグラフ系ツールの実行"""

from __future__ import annotations

from typing import Any, Callable, Dict

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    append_inner_thought_to_message,
    exception_result,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_USE_ITEM,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)
from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.application.world_graph.prepared_action_registry import PreparedActionRegistry
from ai_rpg_world.application.world_graph.synchronized_action_registry import (
    SynchronizedActionRegistry,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import SpotGraphWorldServices
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
)
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotPlayerPreparedActionEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId
from ai_rpg_world.domain.world_graph.value_object.synchronized_action_group import (
    SynchronizedActionGroup,
)


class SpotGraphToolExecutor:
    """spot_graph_* ツールのハンドラを提供する。"""

    def __init__(
        self,
        spot_graph_world_services: SpotGraphWorldServices,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
        event_publisher: Any = None,
        *,
        sync_action_groups: tuple[SynchronizedActionGroup, ...] = (),
        time_provider: GameTimeProvider | None = None,
        spot_graph_repository: ISpotGraphRepository | None = None,
    ) -> None:
        if spot_graph_world_services.movement is None:
            raise TypeError("SpotGraphWorldServices.movement が必要です")
        self._svc = spot_graph_world_services
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        self._event_publisher = event_publisher
        # 協力ギミック #13 用: 既知の sync group と現在 tick provider。
        # 渡されない場合は sync 関連の追加処理（observation 発火、tick 記録）
        # は行わず、従来の prepare 挙動だけになる。
        self._sync_action_groups = sync_action_groups
        self._time_provider = time_provider
        self._spot_graph_repository = spot_graph_repository

    def get_handlers(self) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        return {
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO: self._travel_to,
            TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION: self._set_sub_location,
            TOOL_NAME_SPOT_GRAPH_EXPLORE: self._explore,
            TOOL_NAME_SPOT_GRAPH_INTERACT: self._interact,
            TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION: self._prepare_action,
            TOOL_NAME_SPOT_GRAPH_USE_ITEM: self._use_item,
            TOOL_NAME_SPOT_GRAPH_WAIT: self._wait,
        }

    def _travel_to(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        raw = args.get("destination_spot_id")
        try:
            dest = int(raw) if raw is not None else 0
        except (TypeError, ValueError):
            return LlmCommandResultDto(
                success=False,
                message="destination_spot_id が不正です（Resolver による解決に失敗した可能性があります）。",
                error_code="INVALID_ARGUMENT",
                remediation=get_remediation("INVALID_ARGUMENT"),
            )
        if dest <= 0:
            return LlmCommandResultDto(success=False, message="destination_spot_id は正の整数です。")
        try:
            inv = self._player_inventory_repository.find_by_id(PlayerId(player_id))
            if inv is None:
                return LlmCommandResultDto(success=False, message="インベントリが見つかりません。")
            owned = collect_owned_item_spec_ids_from_inventory(inv, self._item_repository)
            flags = self._svc.world_flags.as_frozen_set()
            self._svc.movement.start_travel_to_spot(
                PlayerId(player_id),
                SpotId.create(dest),
                owned,
                flags,
            )
            base = f"スポット {dest} への移動を開始しました。"
            return LlmCommandResultDto(
                success=True, message=append_inner_thought_to_message(base, args)
            )
        except Exception as e:
            return exception_result(e)

    def _set_sub_location(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        raw = args.get("sub_location_id")
        sub: SubLocationId | None
        try:
            if raw is None or raw == 0:
                sub = None
            else:
                sub = SubLocationId.create(int(raw))
        except (TypeError, ValueError):
            return LlmCommandResultDto(success=False, message="sub_location_id が不正です。")
        try:
            self._svc.movement.move_to_sub_location(PlayerId(player_id), sub)
            return LlmCommandResultDto(
                success=True,
                message=append_inner_thought_to_message(
                    "サブロケーションを更新しました。", args
                ),
            )
        except Exception as e:
            return exception_result(e)

    def _explore(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        try:
            result = self._svc.exploration.explore_once(PlayerId(player_id))
            parts = list(result.discovery_descriptions)
            if result.item_spec_ids_granted:
                parts.append(f"アイテム付与: {len(result.item_spec_ids_granted)} 種")
            msg = "\n".join(parts) if parts else "特に新しい発見はありませんでした。"
            return LlmCommandResultDto(
                success=True, message=append_inner_thought_to_message(msg, args)
            )
        except Exception as e:
            return exception_result(e)

    def _interact(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        try:
            oid = int(args.get("object_id", 0))
            action = str(args.get("action_name", "")).strip()
        except (TypeError, ValueError):
            return LlmCommandResultDto(success=False, message="object_id / action_name が不正です。")
        if oid <= 0 or not action:
            return LlmCommandResultDto(success=False, message="object_id と action_name を指定してください。")
        interaction_parameters = args.get("parameters")
        try:
            out = self._svc.interaction.execute_interaction(
                PlayerId(player_id),
                SpotObjectId.create(oid),
                action,
                interaction_parameters=interaction_parameters,
            )
            msg = "\n".join(out.messages) if out.messages else "操作を実行しました。"
            return LlmCommandResultDto(
                success=True, message=append_inner_thought_to_message(msg, args)
            )
        except Exception as e:
            return exception_result(e)

    def _use_item(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        item_spec_id = args.get("item_spec_id")
        if item_spec_id is None:
            return LlmCommandResultDto(success=False, message="item_spec_id を指定してください。")
        try:
            item_spec_id_int = int(item_spec_id)
        except (TypeError, ValueError):
            return LlmCommandResultDto(success=False, message="item_spec_id が不正です。")
        try:
            from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId as ISpecId
            inv = self._player_inventory_repository.find_by_id(PlayerId(player_id))
            if inv is None:
                return LlmCommandResultDto(success=False, message="インベントリが見つかりません。")
            target_spec = ISpecId.create(item_spec_id_int)
            # インベントリからアイテムインスタンスを探す
            item_instance = None
            for slot in inv.slots:
                if slot.item_instance_id is None:
                    continue
                item = self._item_repository.find_by_id(slot.item_instance_id)
                if item is not None and item.item_spec.item_spec_id == target_spec:
                    item_instance = item
                    break
            if item_instance is None:
                return LlmCommandResultDto(success=False, message="そのアイテムは持っていません。")
            from ai_rpg_world.domain.item.enum.item_enum import ItemType
            if item_instance.item_spec.item_type != ItemType.CONSUMABLE:
                return LlmCommandResultDto(success=False, message="このアイテムは消費できません。")
            item_instance.use()
            if item_instance.quantity == 0:
                self._item_repository.delete(item_instance.item_instance_id)
                inv.remove_item_for_placement(slot.slot_id)
                self._player_inventory_repository.save(inv)
            else:
                self._item_repository.save(item_instance)
            # EventPublisher 経由で ConsumableUsedEvent を発行
            # → ConsumableEffectHandler が HP/MP 回復等を適用
            if (
                self._event_publisher is not None
                and item_instance.item_spec.consume_effect is not None
            ):
                from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent
                self._event_publisher.publish(
                    ConsumableUsedEvent.create(
                        aggregate_id=PlayerId(player_id),
                        aggregate_type="PlayerStatusAggregate",
                        item_spec_id=item_instance.item_spec.item_spec_id,
                    )
                )
            name = item_instance.item_spec.name
            base = f"{name}を使用した。"
            if item_instance.item_spec.consume_effect is not None:
                base += f"（効果が適用された）"
            return LlmCommandResultDto(
                success=True,
                message=append_inner_thought_to_message(base, args),
            )
        except Exception as e:
            return exception_result(e)

    def _prepare_action(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        action_id = str(args.get("action_id", "")).strip()
        if not action_id:
            return LlmCommandResultDto(success=False, message="action_id を指定してください。")
        try:
            registry = PreparedActionRegistry(self._svc.world_flags)
            registry.prepare(player_id=player_id, action_id=action_id)
            # 協力ギミック #13: action_id が sync group に属していれば、
            # tick 付きで SynchronizedActionRegistry にも記録し、観測を出す。
            self._maybe_register_sync_prepare(player_id, action_id)
            base = f"アクション「{action_id}」の準備をした。他のプレイヤーが対応する操作を実行できるようになった。"
            return LlmCommandResultDto(
                success=True,
                message=append_inner_thought_to_message(base, args),
            )
        except ValueError as ve:
            return LlmCommandResultDto(success=False, message=str(ve))
        except Exception as e:
            return exception_result(e)

    def _maybe_register_sync_prepare(self, player_id: int, action_id: str) -> None:
        """action_id が sync group に属していれば tick 付き登録 + 観測発火。"""
        if not self._sync_action_groups or self._time_provider is None:
            return
        matching = [
            g for g in self._sync_action_groups
            if action_id in g.required_action_ids
        ]
        if not matching:
            return
        current_tick = self._time_provider.get_current_tick()
        sync_registry = SynchronizedActionRegistry(self._svc.world_flags)
        sync_registry.prepare(
            action_id=action_id,
            player_id=player_id,
            current_tick=current_tick.value,
        )
        # 観測発火: 各 group の on_prepare_observation_message を持つもののみ
        if self._event_publisher is None or self._spot_graph_repository is None:
            return
        # actor のスポット情報を取得
        try:
            graph = self._spot_graph_repository.find_graph()
            spot_id = graph.get_entity_spot(EntityId.create(player_id))
        except Exception:
            return
        events = []
        for g in matching:
            if not g.on_prepare_observation_message:
                continue
            events.append(
                SpotPlayerPreparedActionEvent.create(
                    aggregate_id=graph.graph_id,
                    aggregate_type="SpotGraphAggregate",
                    entity_id=EntityId.create(player_id),
                    spot_id=spot_id,
                    action_id=action_id,
                    group_id=g.group_id,
                    observation_message=g.on_prepare_observation_message,
                )
            )
        if events:
            self._event_publisher.publish_all(events)

    def _wait(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        del player_id
        reason = str(args.get("reason", "")).strip()
        if self._svc.simulation is None:
            return LlmCommandResultDto(
                success=False,
                message="wait は現在のワイヤリングでは未対応です。",
                error_code="UNSUPPORTED_TOOL",
            )
        try:
            tick = self._svc.simulation.tick()
            suffix = f"（理由: {reason}）" if reason else ""
            base = f"待機して時間が進んだ: tick={tick.value}{suffix}"
            return LlmCommandResultDto(
                success=True,
                message=append_inner_thought_to_message(base, args),
            )
        except Exception as e:
            return exception_result(e)
