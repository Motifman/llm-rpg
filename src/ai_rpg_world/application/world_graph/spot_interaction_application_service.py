from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

_logger = logging.getLogger(__name__)

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
from ai_rpg_world.domain.world_graph.enum.passage_change_cause import (
    PassageChangeCauseEnum,
)
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import ISpotInteriorRepository
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import SpotInteractionService
from ai_rpg_world.domain.world_graph.value_object.applied_effect_summary import (
    AppliedEffectKind,
    AppliedEffectSummary,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotObjectInteractedEvent,
    SpotObjectInteractionFailedEvent,
    SpotObjectStateChangedEvent,
    SpotPlayerStateChangedInSpotEvent,
    SpotPublicEffectObservedEvent,
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
    # Phase 4-E: 行為者本人にツール結果として返す直接効果サマリ。
    # 観測ストリームには流さない（同じ事象を二重に受け取らないため）。
    direct_effects: Tuple[AppliedEffectSummary, ...] = ()


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

    def set_event_publisher(self, event_publisher: Any) -> None:
        """event_publisher を後付けで注入する (二段構築用)。

        通常は constructor で渡すのが望ましいが、escape_game の
        ``create_escape_game_runtime`` のように publisher が runtime
        本体に依存して構築順序的に後になるケースで使う。

        旧コードは ``interaction_service._event_publisher = ...`` と
        private field に直接代入していたため、本メソッドで正規化する。
        """
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

        # Phase 4-D-1: プレイヤー状態 (HP / needs) を precondition から
        # 参照できるように aggregate を load して domain service に渡す。
        # repository 注入が無い場合は None を渡し、player precondition は
        # silent failure 回避のため拒否する (silent pass を避ける domain 規約)。
        acting_player_status = None
        if self._player_status_repository is not None:
            acting_player_status = self._player_status_repository.find_by_id(player_id)

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
                acting_player_status=acting_player_status,
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
                cause=PassageChangeCauseEnum.ACTOR_ACTION,
                # Issue #183: 連鎖の起点を ConnectionStateChangedEvent に伝える。
                # observer 側で「同 spot で actor を視認できるか」を判定して
                # prose を組み立てるために使う (軸 1 + 4)。
                actor_entity_id=entity_id,
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

        # Phase 4-D-2: 行動者プレイヤーの自由 state が effect で変わった場合、
        # player_status_repository に save して永続化する。
        # in-place 変更された aggregate (acting_player_status) をそのまま渡す。
        if (
            result.acting_player_state_changed
            and acting_player_status is not None
            and self._player_status_repository is not None
        ):
            self._player_status_repository.save(acting_player_status)

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

        # Phase G (#3): APPLY_DAMAGE 接触ダメージの実体化。
        # effect_service が damage_specs を組み立てるところまでは出来ていたが、
        # interaction application service が消費していなかったため、JSON で
        # APPLY_DAMAGE を書いても何も起きない無効化状態だった (廃屋の崩れた梁・
        # 岩礁の崖・沼地のぬかるみ等が flavor 止まり)。
        # ここで PlayerStatusAggregate.apply_damage を呼んで HP を減らす。HP 0 に
        # なれば aggregate が PlayerDownedEvent を積み、event publisher 経由で
        # PlayerDownedOutcomeHandler が DEAD outcome を確定させる (E-3a 経路)。
        if result.damage_specs and self._player_status_repository is not None:
            status = self._player_status_repository.find_by_id(player_id)
            if status is not None:
                for spec in result.damage_specs:
                    if spec.damage <= 0:
                        continue  # 0 ダメージは no-op
                    status.apply_damage(spec.damage)
                self._player_status_repository.save(status)

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
            # Phase 4-E: PUBLIC_OBSERVABLE な効果サマリを同スポットの他プレイヤーに
            # 観測として届ける。actor は recipient strategy 側で除外される。
            # ACTOR_DIRECT は result.direct_effects 経由でツール結果として、
            # HIDDEN は誰にも届けず本人プロンプトの現在状態にのみ載せる。
            public_events = self._build_public_observable_events(
                public_summaries=result.public_observable_effects,
                graph_id=graph.graph_id,
                spot_id=spot_id,
                actor_entity_id=entity_id,
                object_id=object_id,
            )
            self._event_publisher.publish_all(
                [*graph_events, interacted_event, *public_events]
            )

        return SpotInteractionResultDto(
            messages=result.messages,
            direct_effects=result.direct_effects,
        )

    def _build_public_observable_events(
        self,
        *,
        public_summaries: Tuple[AppliedEffectSummary, ...],
        graph_id: Any,
        spot_id: SpotId,
        actor_entity_id: EntityId,
        object_id: SpotObjectId,
    ) -> list:
        """PUBLIC_OBSERVABLE な AppliedEffectSummary を観測 event 列に翻訳する。

        - SPOT_OBJECT_STATE_CHANGE → SpotObjectStateChangedEvent
          (actor_entity_id を埋めて recipient 側で actor を除外)
        - ACTING_PLAYER_STATE_CHANGE → SpotPlayerStateChangedInSpotEvent
        - その他 (DAMAGE / TELEPORT / ATMOSPHERE / PASSAGE / CONNECTION 等) は
          PR2 範囲では既存の専用 event 経路に任せる: ConnectionStateChangedEvent
          は graph aggregate が独自に発火するため、ここで重複発火しない。
          DAMAGE / ATMOSPHERE はまだ第三者観測経路を持たないが、必要になったら
          後続 PR で追加する。
        """
        events: list = []
        for summary in public_summaries:
            if summary.kind == AppliedEffectKind.SPOT_OBJECT_STATE_CHANGE:
                events.append(
                    SpotObjectStateChangedEvent.create(
                        aggregate_id=graph_id,
                        aggregate_type="SpotGraphAggregate",
                        spot_id=spot_id,
                        object_id=object_id,
                        old_state=_state_from_delta_before(summary.state_delta),
                        new_state=_state_from_delta_after(summary.state_delta),
                        actor_entity_id=actor_entity_id,
                        state_delta=summary.state_delta,
                    )
                )
            elif summary.kind == AppliedEffectKind.ACTING_PLAYER_STATE_CHANGE:
                # observation_message は空にする。AppliedEffectSummary.description
                # は「プレイヤー自身の状態が変化した」のような汎用文字列で、
                # bystander 視点では情報量が無い。formatter には state_delta から
                # 「Aliceの〜が〜から〜に変わった」を組み立てさせる。
                # シナリオ作家が具体的な観測テキストを出したい場合は
                # 別 effect (例: SHOW_MESSAGE) を併用する想定。
                events.append(
                    SpotPlayerStateChangedInSpotEvent.create(
                        aggregate_id=graph_id,
                        aggregate_type="SpotGraphAggregate",
                        entity_id=actor_entity_id,
                        spot_id=spot_id,
                        state_delta=summary.state_delta,
                        observation_message="",
                    )
                )
            elif summary.kind in (
                AppliedEffectKind.DAMAGE,
                AppliedEffectKind.STATUS_EFFECT,
                AppliedEffectKind.SATISFY_NEED,
                AppliedEffectKind.ATMOSPHERE_UPDATE,
                AppliedEffectKind.TARGET_ITEM_STATE_CHANGE,
                AppliedEffectKind.ACTING_ITEM_STATE_CHANGE,
            ):
                # Phase 4-E PR 3: 専用 event を持たない汎用 public observable
                # 効果は SpotPublicEffectObservedEvent に乗せて第三者へ届ける。
                # ACTING_ITEM_STATE_CHANGE は通常 ACTOR_DIRECT (デフォルト) で
                # ここに来ないが、シナリオが PUBLIC_OBSERVABLE に上書きした
                # ケース (例: 派手に光るアイテムの状態変化) では届ける。
                events.append(
                    SpotPublicEffectObservedEvent.create(
                        aggregate_id=graph_id,
                        aggregate_type="SpotGraphAggregate",
                        spot_id=spot_id,
                        actor_entity_id=actor_entity_id,
                        kind=summary.kind,
                        description=summary.description,
                        target_ref=summary.target_ref,
                        state_delta=summary.state_delta,
                    )
                )
            elif summary.kind == AppliedEffectKind.TELEPORT:
                # TELEPORT_ENTITY effect は spec を生成するだけで実際の
                # entity 移動はまだ実装されていない (dead code)。entity が
                # 実際に消える瞬間は EntityLeftSpotEvent が担う設計のはずな
                # ので、ここで重複発火しない。実装が入った時点で再評価する。
                _logger.debug(
                    "PR3: TELEPORT summary observed but entity movement is not "
                    "wired yet; skipping observation event"
                )
            else:
                # PASSAGE_STATE_UPDATE / CONNECTION_CREATED / CONNECTION_DESTROYED
                # は graph aggregate が ConnectionStateChangedEvent /
                # ConnectionCreatedEvent / ConnectionDestroyedEvent をそれぞれ
                # 自前で発火するので、ここで重複発火しない。
                _logger.debug(
                    "PR3: summary kind %s is delivered via graph aggregate "
                    "events; skipping",
                    summary.kind.value,
                )
        return events

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


def _state_from_delta_before(delta: Tuple[Any, ...]) -> Dict[str, Any]:
    """state_delta の before 値から old_state 互換 dict を再構築する。

    LOSSY: before が None だったキー (新規追加 / 元から None) は dict に
    含めない。`SpotObjectStateChangedEvent` の old_state/new_state は既存
    の event 署名を保ったままにするための互換ビューに過ぎず、formatter は
    state_delta を優先して読む。before が None で値が新規追加されるケースを
    正確に再構築したい future consumer は state_delta を直接読むこと。
    """
    return {d.key: d.before for d in delta if d.before is not None}


def _state_from_delta_after(delta: Tuple[Any, ...]) -> Dict[str, Any]:
    """state_delta の after 値から new_state 互換 dict を再構築する。

    LOSSY: after が None (= 削除) のキーは dict に含めない。詳細は
    `_state_from_delta_before` を参照。
    """
    return {d.key: d.after for d in delta if d.after is not None}
