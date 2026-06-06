"""スポットグラフ系ツールの実行"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.failure_helpers import (
    build_invalid_arg_failure,
    build_sanitized_exception_failure,
)
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    append_inner_thought_to_message,
    exception_result,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_ATTACK,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
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
from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
    SpotAttackOrchestrator,
)
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import SpotGraphWorldServices
from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
    ItemTransferException,
    SpotGraphItemTransferService,
)
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


# Phase F: 腐敗食を食べた時のダメージ量 (HP)。
# 当面ハードコードで、per-item config 化は将来の PR で行う。
# 10 は base_stats.max_hp=100 (現状の survival demo) に対して 10% 程度で、
# 1 度の事故では致命的にならないが、繰り返せば確実に死ぬバランス。
SPOILED_FOOD_DAMAGE_HP = 10


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
        sync_action_registry: SynchronizedActionRegistry | None = None,
        monster_repository: Optional[MonsterRepository] = None,
        player_status_repository: Optional[PlayerStatusRepository] = None,
        attack_orchestrator: Optional[SpotAttackOrchestrator] = None,
        item_transfer_service: Optional["SpotGraphItemTransferService"] = None,
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
        # resolver stage と同一 instance を共有することで、将来 registry に
        # 状態（キャッシュ等）が増えても乖離しない。渡されない場合は
        # 既定で world_flags を使う独立 instance を生成（後方互換）。
        self._sync_action_registry = (
            sync_action_registry
            or SynchronizedActionRegistry(spot_graph_world_services.world_flags)
        )
        # 戦闘ツール (`spot_graph_attack`) で使用。注入されていない構成では
        # `_attack` が「未対応」エラーを返す（後方互換 + minimal wiring 構成
        # のため）。
        self._monster_repository = monster_repository
        self._player_status_repository = player_status_repository
        # attack_orchestrator が注入されていれば優先利用。注入されない場合は
        # 内部でリポジトリから組み立てる（後方互換: 旧 wiring が orchestrator
        # を渡さず monster/player リポジトリだけ渡してきても動く）。
        self._attack_orchestrator = attack_orchestrator
        # 注入されない構成では drop/pickup ハンドラは「未対応」エラーを返す
        # (後方互換 + minimal wiring 用)。
        self._item_transfer_service = item_transfer_service

    def get_handlers(self) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        return {
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO: self._travel_to,
            TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION: self._set_sub_location,
            TOOL_NAME_SPOT_GRAPH_EXPLORE: self._explore,
            TOOL_NAME_SPOT_GRAPH_INTERACT: self._interact,
            TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION: self._prepare_action,
            TOOL_NAME_SPOT_GRAPH_USE_ITEM: self._use_item,
            TOOL_NAME_SPOT_GRAPH_DROP_ITEM: self._drop_item,
            TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM: self._pickup_item,
            TOOL_NAME_SPOT_GRAPH_GIVE_ITEM: self._give_item,
            TOOL_NAME_SPOT_GRAPH_ATTACK: self._attack,
            TOOL_NAME_SPOT_GRAPH_LISTEN: self._listen,
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
            return build_invalid_arg_failure(
                arg_name="destination_spot_id",
                detail="正の整数を指定してください",
            )
        try:
            inv = self._player_inventory_repository.find_by_id(PlayerId(player_id))
            if inv is None:
                return LlmCommandResultDto(
                    success=False,
                    message="インベントリが見つかりません。",
                    error_code="PLAYER_NOT_FOUND",
                    remediation=get_remediation("PLAYER_NOT_FOUND"),
                )
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
            return build_invalid_arg_failure(
                arg_name="sub_location_id",
                detail="正の整数または 0/None を指定してください",
            )
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
            return build_invalid_arg_failure(
                arg_name="object_id / action_name",
                detail="object_id は正の整数、action_name は非空の文字列",
            )
        if oid <= 0 or not action:
            return build_invalid_arg_failure(
                arg_name="object_id / action_name",
                detail="object_id (正の整数) と action_name (非空文字列) を必ず指定してください",
            )
        interaction_parameters = args.get("parameters")
        try:
            out = self._svc.interaction.execute_interaction(
                PlayerId(player_id),
                SpotObjectId.create(oid),
                action,
                interaction_parameters=interaction_parameters,
                current_tick=self._time_provider.get_current_tick(),
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
            return build_invalid_arg_failure(
                arg_name="item_spec_id",
                detail="使用するアイテムの spec_id (正の整数) を指定してください",
            )
        try:
            item_spec_id_int = int(item_spec_id)
        except (TypeError, ValueError):
            return build_invalid_arg_failure(
                arg_name="item_spec_id",
                detail="正の整数を指定してください",
            )
        try:
            from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId as ISpecId
            inv = self._player_inventory_repository.find_by_id(PlayerId(player_id))
            if inv is None:
                return LlmCommandResultDto(
                    success=False,
                    message="インベントリが見つかりません。",
                    error_code="PLAYER_NOT_FOUND",
                    remediation=get_remediation("PLAYER_NOT_FOUND"),
                )
            target_spec = ISpecId.create(item_spec_id_int)
            # インベントリからアイテムインスタンスを探す。
            # 実験 #26 で発覚: 旧コードは `inv.slots` (存在しない属性) を iter して
            # 全 use_item が AttributeError → SYSTEM_ERROR (72 件) で死んでいた。
            # PR #385 で `_inventory_slots.items()` 直接 iter に hot fix した後、
            # 本 PR で aggregate 側の公開 API `find_slot_by_item_spec_id` に
            # 切り替え、private 属性への直接アクセスを完全廃止 (恒久対策)。
            found = inv.find_slot_by_item_spec_id(target_spec, self._item_repository)
            item_instance = None
            matched_slot_id = None
            if found is not None:
                matched_slot_id, iid = found
                item_instance = self._item_repository.find_by_id(iid)
            if item_instance is None:
                return LlmCommandResultDto(
                    success=False,
                    message="指定したアイテムは持っていません。",
                    error_code="ITEM_NOT_FOUND",
                    remediation=get_remediation("ITEM_NOT_FOUND"),
                )
            from ai_rpg_world.domain.item.enum.item_enum import ItemType
            if item_instance.item_spec.item_type != ItemType.CONSUMABLE:
                return LlmCommandResultDto(
                    success=False,
                    message="このアイテムは消費できません (CONSUMABLE 種別ではない)。",
                    error_code="ITEM_NOT_CONSUMABLE",
                    remediation=get_remediation("ITEM_NOT_CONSUMABLE"),
                )
            # Phase F: 腐敗食を食べたか判定する。use() で quantity が減って
            # state がリセットされる前に読む必要があるのでここで取る。
            # 集約は (spec, spoiled) ベースで slot に分かれて入っているはずなので、
            # 同 slot の instance が「腐敗 / 新鮮」のどちらかに確定している前提。
            is_spoiled = bool(item_instance.state.get("spoiled"))
            item_instance.use()
            # ItemUsedEvent / ItemBrokenEvent は ItemAggregate.use() で aggregate
            # に積まれる。これらは publish しないと durability ベースの
            # observation / metrics が silent に落ちるため、ここで drain して
            # event_publisher に流す。新鮮パスでは下流で ConsumableUsedEvent も
            # 別途 publish される。
            instance_events = list(item_instance.get_events())
            item_instance.clear_events()
            if instance_events and self._event_publisher is not None:
                self._event_publisher.publish_all(instance_events)
            if item_instance.quantity == 0:
                # 順序が重要: inventory から slot を空ける処理を先に save し、
                # その後に item_repository から物理削除する。これを逆順に
                # すると delete 成功・inventory save 失敗のときに、誰も持って
                # いない slot に存在しない item_instance_id が残り続け、
                # 以降の lookup が全部 None になる silent failure を生む。
                if matched_slot_id is not None:
                    inv.remove_item_for_placement(matched_slot_id)
                self._player_inventory_repository.save(inv)
                self._item_repository.delete(item_instance.item_instance_id)
            else:
                self._item_repository.save(item_instance)
            name = item_instance.item_spec.name
            if is_spoiled:
                # Phase F: 腐敗食 → ConsumableUsedEvent を出さず、直接ダメージを
                # PlayerStatusAggregate に適用する。回復効果は捨てる (handler 経路
                # を通さない)。damage 量は当面ハードコード (10)。per-item config
                # は別 PR で。
                damage = SPOILED_FOOD_DAMAGE_HP
                # 防御: 最小 wiring (テスト等) で _player_status_repository=None
                # でインスタンス化された場合に AttributeError を投げないよう
                # ガード。本ガードに当たるのは構成ミス相当で、damage は適用
                # できないが silent crash よりは LLM に「効果が適用されなかっ
                # た」を返す方が学習可能。
                if self._player_status_repository is None:
                    return LlmCommandResultDto(
                        success=True,
                        message=append_inner_thought_to_message(
                            f"{name}を食べてしまった。腐っていたが体への効果は記録されなかった。",
                            args,
                        ),
                    )
                status = self._player_status_repository.find_by_id(PlayerId(player_id))
                if status is not None:
                    status.apply_damage(damage)
                    self._player_status_repository.save(status)
                    # Phase G silent-failure fix: apply_damage が HP 0 にした
                    # 場合 aggregate は PlayerDownedEvent を積む。event_publisher
                    # に流さないと PlayerDownedOutcomeHandler が走らず、
                    # 腐敗食で死んでも DEAD outcome が立たない silent 破綻に
                    # なる。new 鮮 path が ConsumableUsedEvent を publish する
                    # のと同様に、spoiled path でも aggregate events を
                    # publish_all で流す。
                    if self._event_publisher is not None:
                        status_events = list(status.get_events())
                        status.clear_events()
                        if status_events:
                            self._event_publisher.publish_all(status_events)
                base = (
                    f"{name}を食べてしまった。腐っていた——胃の奥が灼ける。"
                    f"（{damage} ダメージ）"
                )
                return LlmCommandResultDto(
                    success=True,
                    message=append_inner_thought_to_message(base, args),
                )
            # 通常 (新鮮) パス: ConsumableUsedEvent を発行
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
            return build_invalid_arg_failure(
                arg_name="action_id",
                detail="準備するアクションの ID (非空文字列) を指定してください",
            )
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
            # ValueError は registry の引数検証 (action_id 空など) で起きる想定。
            # str(ve) を LLM に直渡しすると path / 内部 ID を漏らす経路になり得るので、
            # サニタイズ + サーバ側ログを残す (PR #170 と同じ pattern)。
            return build_sanitized_exception_failure(
                exc=ve,
                log_context=(
                    f"spot_graph_prepare_action validation failure "
                    f"player_id={player_id} action_id={action_id!r}"
                ),
                public_message=(
                    f"action_id={action_id!r} の準備に失敗しました。"
                    "シナリオで定義済みの action_id を指定してください。"
                ),
                error_code="INVALID_ARGUMENT",
            )
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
        sync_registry = self._sync_action_registry
        # MEDIUM-2: 同 player+action_id が既に登録済みなら観測の重複を避ける。
        # （tick だけ更新する形で prepare し直し、観測は出さない。）
        already_prepared_by_same_player = any(
            e.player_id == player_id
            for e in sync_registry.entries_for(action_id)
        )
        sync_registry.prepare(
            action_id=action_id,
            player_id=player_id,
            current_tick=current_tick.value,
        )
        if already_prepared_by_same_player:
            return
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

    def _drop_item(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        """`spot_graph_drop_item`: 所持アイテムを現在地の地面に置く。

        resolver で slot_id / item_instance_id / target_display_name まで解決済み。
        本ハンドラは SpotGraphItemTransferService に委譲してインベントリから地面
        への転送だけ行う。同室者への観測注入は Phase 19 で event 経由で行う。
        """
        if self._item_transfer_service is None:
            return LlmCommandResultDto(
                success=False,
                message="drop_item は本構成で未配線です。",
                error_code="NOT_WIRED",
                remediation=get_remediation("NOT_WIRED"),
            )
        slot_id_raw = args.get("slot_id")
        if slot_id_raw is None:
            return build_invalid_arg_failure(
                arg_name="slot_id",
                detail="resolver が slot_id を埋めませんでした (label 解決失敗の可能性)",
            )
        try:
            slot_id_int = int(slot_id_raw)
        except (TypeError, ValueError):
            return build_invalid_arg_failure(
                arg_name="slot_id", detail="slot_id は整数で指定してください"
            )
        from ai_rpg_world.domain.player.value_object.slot_id import SlotId
        from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
        # Phase C: stealth=true なら ACTOR_ONLY、それ以外は従来通り SAME_SPOT
        policy = (
            WitnessPolicy.ACTOR_ONLY if bool(args.get("stealth", False))
            else WitnessPolicy.SAME_SPOT
        )
        try:
            result = self._item_transfer_service.drop_item(
                PlayerId(player_id), SlotId(slot_id_int),
                witness_policy=policy,
            )
            msg = "; ".join(result.messages) if result.messages else "地面に置いた。"
            return LlmCommandResultDto(
                success=True, message=append_inner_thought_to_message(msg, args)
            )
        except ItemTransferException as e:
            return LlmCommandResultDto(
                success=False,
                message=f"アイテムを落とせません: {e}",
                error_code="ITEM_TRANSFER_FAILED",
                remediation=get_remediation("ITEM_TRANSFER_FAILED"),
            )
        except Exception as e:
            return exception_result(e)

    def _pickup_item(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        """`spot_graph_pickup_item`: 現在地の地面アイテムを拾う。

        resolver で item_instance_id / target_display_name まで解決済み。
        """
        if self._item_transfer_service is None:
            return LlmCommandResultDto(
                success=False,
                message="pickup_item は本構成で未配線です。",
                error_code="NOT_WIRED",
                remediation=get_remediation("NOT_WIRED"),
            )
        iid_raw = args.get("item_instance_id")
        if iid_raw is None:
            return build_invalid_arg_failure(
                arg_name="item_instance_id",
                detail="resolver が item_instance_id を埋めませんでした",
            )
        try:
            iid_int = int(iid_raw)
        except (TypeError, ValueError):
            return build_invalid_arg_failure(
                arg_name="item_instance_id",
                detail="item_instance_id は整数で指定してください",
            )
        from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
        from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
        policy = (
            WitnessPolicy.ACTOR_ONLY if bool(args.get("stealth", False))
            else WitnessPolicy.SAME_SPOT
        )
        try:
            result = self._item_transfer_service.pickup_item(
                PlayerId(player_id), ItemInstanceId.create(iid_int),
                witness_policy=policy,
            )
            msg = "; ".join(result.messages) if result.messages else "拾い上げた。"
            return LlmCommandResultDto(
                success=True, message=append_inner_thought_to_message(msg, args)
            )
        except ItemTransferException as e:
            return LlmCommandResultDto(
                success=False,
                message=f"アイテムを拾えません: {e}",
                error_code="ITEM_TRANSFER_FAILED",
                remediation=get_remediation("ITEM_TRANSFER_FAILED"),
            )
        except Exception as e:
            return exception_result(e)

    def _give_item(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        """`spot_graph_give_item`: 同室の別プレイヤーへアイテムを渡す。

        resolver で slot_id / target_player_id まで解決済み。
        """
        if self._item_transfer_service is None:
            return LlmCommandResultDto(
                success=False,
                message="give_item は本構成で未配線です。",
                error_code="NOT_WIRED",
                remediation=get_remediation("NOT_WIRED"),
            )
        slot_raw = args.get("slot_id")
        to_raw = args.get("target_player_id")
        if slot_raw is None or to_raw is None:
            return build_invalid_arg_failure(
                arg_name="slot_id / target_player_id",
                detail="resolver が引数を埋めませんでした (label 解決失敗の可能性)",
            )
        try:
            slot_int = int(slot_raw)
            to_int = int(to_raw)
        except (TypeError, ValueError):
            return build_invalid_arg_failure(
                arg_name="slot_id / target_player_id",
                detail="整数で指定してください",
            )
        from ai_rpg_world.domain.player.value_object.slot_id import SlotId
        try:
            result = self._item_transfer_service.give_item(
                PlayerId(player_id), PlayerId(to_int), SlotId(slot_int),
            )
            msg = "; ".join(result.messages) if result.messages else "渡した。"
            return LlmCommandResultDto(
                success=True, message=append_inner_thought_to_message(msg, args)
            )
        except ItemTransferException as e:
            return LlmCommandResultDto(
                success=False,
                message=f"アイテムを渡せません: {e}",
                error_code="ITEM_TRANSFER_FAILED",
                remediation=get_remediation("ITEM_TRANSFER_FAILED"),
            )
        except Exception as e:
            return exception_result(e)

    def _attack(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        """`spot_graph_attack`: 同スポットのモンスターを攻撃する。

        resolver で `monster_id` / `target_display_name` まで解決済み。
        実際の attack 処理は `SpotAttackOrchestrator` に委譲し、本ハンドラは:
        1. 必要なリポジトリ + orchestrator + tick provider が揃っているか確認
        2. attacker / target aggregate をロード
        3. orchestrator.execute_player_attack に loaded aggregate を渡す
        4. 戻ってきた `AttackOutcome` を LlmCommandResultDto に変換

        save / event 発火は orchestrator が責任を持つ。失敗系
        （cooldown / target_dead / damage=0 / wiring 不足）は
        `success=False` で返す。
        """
        orchestrator = self._resolve_attack_orchestrator()
        if (
            orchestrator is None
            or self._monster_repository is None
            or self._player_status_repository is None
            or self._spot_graph_repository is None
            or self._time_provider is None
        ):
            return LlmCommandResultDto(
                success=False,
                message="attack は現在のワイヤリングでは未対応です。",
                error_code="UNSUPPORTED_TOOL",
            )

        monster_id_int = args.get("monster_id")
        if not isinstance(monster_id_int, int):
            return LlmCommandResultDto(
                success=False,
                message="monster_id が解決されていません。",
                error_code="INVALID_TARGET_LABEL",
            )
        display_name = str(args.get("target_display_name", "")).strip() or "モンスター"

        monster_id = MonsterId.create(monster_id_int)
        try:
            monster = self._monster_repository.find_by_id(monster_id)
            if monster is None:
                return LlmCommandResultDto(
                    success=False,
                    message=f"対象のモンスターが見つかりません: {display_name}",
                    error_code="TARGET_NOT_FOUND",
                )
            attacker = self._player_status_repository.find_by_id(PlayerId(player_id))
            if attacker is None:
                return LlmCommandResultDto(
                    success=False,
                    message="プレイヤー情報が見つかりません。",
                    error_code="PLAYER_NOT_FOUND",
                )

            graph = self._spot_graph_repository.find_graph()
            current_tick = self._time_provider.get_current_tick()
            outcome = orchestrator.execute_player_attack(
                attacker_player=attacker,
                target_monster=monster,
                graph=graph,
                current_tick=current_tick,
            )
            if not outcome.executed:
                return LlmCommandResultDto(
                    success=False,
                    message=f"{display_name}を攻撃できなかった ({outcome.reason})。",
                    error_code="ATTACK_FAILED",
                )

            base = f"{display_name}に {outcome.damage} のダメージを与えた。"
            if outcome.target_incapacitated:
                base += " 致命傷で倒した。"
            return LlmCommandResultDto(
                success=True,
                message=append_inner_thought_to_message(base, args),
            )
        except Exception as e:
            return exception_result(e)

    def _resolve_attack_orchestrator(self) -> Optional[SpotAttackOrchestrator]:
        """attack_orchestrator が注入されていればそれを使い、無ければ
        repository から動的に組み立てる（後方互換）。

        将来、wiring が必ず orchestrator を渡すようになったら本メソッドと
        その下の組み立てロジックは削除して `self._attack_orchestrator` を
        直接使えば良い。
        """
        if self._attack_orchestrator is not None:
            return self._attack_orchestrator
        if (
            self._monster_repository is None
            or self._player_status_repository is None
            or self._spot_graph_repository is None
        ):
            return None
        return SpotAttackOrchestrator(
            spot_graph_repository=self._spot_graph_repository,
            monster_repository=self._monster_repository,
            player_status_repository=self._player_status_repository,
        )

    def _listen(self, player_id: int, args: Dict[str, Any]) -> LlmCommandResultDto:
        """`spot_graph_listen`: 自 spot + 隣接 spot (1 hop 減衰) の環境音を観測する。

        Phase 5 PR-2。`SpotGraphAggregate.emit_listen_carefully` に
        集約された 1 hop 伝搬モデルで `SpotSoundHeardEvent` を発火し、
        recipient strategy 経由で本人にだけ届ける (observer pipeline で
        formatter が prose を組み立てる)。

        本ハンドラは state を変更しないため `save(graph)` は呼ばない。
        event は graph aggregate に積まれるので `get_events()` で抜き、
        `event_publisher.publish_all` で publish する。
        """
        if self._spot_graph_repository is None or self._event_publisher is None:
            return LlmCommandResultDto(
                success=False,
                message="listen は現在のワイヤリングでは未対応です。",
                error_code="UNSUPPORTED_TOOL",
            )
        try:
            graph = self._spot_graph_repository.find_graph()
            entity_id = EntityId.create(player_id)
            graph.emit_listen_carefully(entity_id)
            events = list(graph.get_events())
            graph.clear_events()
            if events:
                self._event_publisher.publish_all(events)
                base = (
                    "耳を澄ました。周囲の音が観測として届いた。"
                    if len(events) == 1
                    else f"耳を澄ました。{len(events)} 箇所からの音が観測として届いた。"
                )
            else:
                # 全 spot が SILENT、または減衰しきって聞こえない場合
                base = "耳を澄ましたが、何も聞こえなかった。"
            return LlmCommandResultDto(
                success=True,
                message=append_inner_thought_to_message(base, args),
            )
        except Exception as e:
            return exception_result(e)

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
