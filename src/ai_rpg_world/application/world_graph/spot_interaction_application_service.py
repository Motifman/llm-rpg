from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

_logger = logging.getLogger(__name__)

from ai_rpg_world.application.common.exceptions import ApplicationException
from ai_rpg_world.application.player.services.departed_position_store import (
    DepartedPositionStore,
)
from ai_rpg_world.application.player.services.player_perception_policy import (
    PlayerPerceptionPolicy,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
    remove_one_item_of_spec_from_inventory,
)
from ai_rpg_world.application.world_graph.interaction_cooldown_store import (
    InteractionCooldownStore,
    object_action_key,
)
from ai_rpg_world.application.world_graph.interaction_wait_text import span_text
from ai_rpg_world.application.world_graph.world_flag_state import (
    MutableWorldFlagState,
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
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
from ai_rpg_world.domain.world_graph.enum.interaction_actor_plane import (
    InteractionActorPlane,
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
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


from ai_rpg_world.application.world_graph.hidden_interaction_filter import (
    is_hidden_from_state,
)


@dataclass(frozen=True)
class SpotInteractionResultDto:
    messages: Tuple[str, ...]
    action_display_label: str
    # Phase 4-E: 行為者本人にツール結果として返す直接効果サマリ。
    # 観測ストリームには流さない（同じ事象を二重に受け取らないため）。
    direct_effects: Tuple[AppliedEffectSummary, ...] = ()


def _hidden_precondition_failed(interaction, actor_state) -> bool:
    """秘匿すべき前提条件で弾かれたか (役割など)。

    判断は ``hidden_interaction_filter`` に 1 つだけ置く。ここに同じ実装を
    書き写していたが、**写しがあると「一覧を作る側は必ずここを通る」が
    構造では保証されない** (claude の指摘)。候補に出さないのと同じ条件を、
    失敗観測でも配らない。
    """
    return is_hidden_from_state(interaction, actor_state)


def _tick_value(current_tick: Any) -> int:
    """WorldTick でも素の int でも現在手番を取り出す。

    行を組み立てる側は provider から素の int を受け取り、実行経路は WorldTick
    を持ち回る。**片方だけを想定すると、もう片方で例外になって待ち時間の断りが
    消える。** 消えた状態は「選べるのに必ず失敗する手」に戻る (#860)。
    """
    return int(getattr(current_tick, "value", current_tick))


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
        # PR4: TIME_OF_DAY_IS / WEATHER_IS condition の評価に使う provider。
        # provider が None なら該当 condition は「不在として fail」する
        # (silent skip を避ける)。シナリオが時間帯 / 天候条件を使うなら
        # 必ず注入が必要。
        time_of_day_phase_provider: Optional[Any] = None,
        weather_type_provider: Optional[Any] = None,
        # #356 後続: 失敗観測の dedup window (tick 単位)。同 (actor, object,
        # action, reason) の失敗が連続したとき、この期間内の 2 回目以降は
        # 観測を emit しない (= LLM の retry loop で同じ失敗観測が 100 回
        # 流れる事態を防ぐ)。デフォルト 24 = survival_island_v2 の 1 day。
        failure_observation_dedup_window: int = 24,
        # PR-F (#710 後続): 看板 (WRITE_PLAYER_TEXT) が object.state に残す
        # 書き手名を解決する resolver。`Callable[[PlayerId], str]` を渡す。
        # None (未注入) の場合はフォールバック名 (`"プレイヤー({id})"`) を使う。
        player_display_name_resolver: Optional[Callable[[PlayerId], str]] = None,
        # PR 3: SPOT_LIGHTING_IS の判定に使う実効照明 resolver。未注入なら
        # 照明条件は成立しない (silent pass させない)。
        effective_lighting_resolver: Optional[Any] = None,
        departed_position_store: Optional[DepartedPositionStore] = None,
        player_perception_policy: Optional[PlayerPerceptionPolicy] = None,
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
        self._time_of_day_phase_provider = time_of_day_phase_provider
        self._weather_type_provider = weather_type_provider
        # 失敗観測 dedup: (entity_id_int, object_id_int, action_name, reason)
        # → last_emit_tick。tick 不明の呼び出しは dedup を skip する。
        self._failure_observation_dedup_window = failure_observation_dedup_window
        self._failure_observation_last_tick: Dict[
            Tuple[int, int, str, str], int
        ] = {}
        self._player_display_name_resolver = player_display_name_resolver
        self._effective_lighting_resolver = effective_lighting_resolver
        self._departed_position_store = departed_position_store
        self._player_perception_policy = player_perception_policy
        self._meeting_caller: Optional[Callable[[PlayerId, str], Any]] = None
        # 物体操作の待ち時間。対人行為と同じ store を共有するので、snapshot も
        # 同じ経路に乗る。別 store を作ると、長走実験の再開で物体側だけ待ち時間が
        # 消える (design_decisions #27 と同じ形の静かな失敗)。
        self._cooldown_store: Optional[InteractionCooldownStore] = None
        self._minutes_per_tick: Optional[int] = None

    def _actor_spot(
        self, player_id: PlayerId, graph: SpotGraphAggregate
    ) -> SpotId:
        if (
            self._player_perception_policy is not None
            and self._player_perception_policy.is_departed(player_id)
        ):
            spot_id = (
                self._departed_position_store.find(player_id)
                if self._departed_position_store is not None
                else None
            )
            if spot_id is None:
                raise ApplicationException(
                    f"去った主体の位置がありません: {player_id}",
                    player_id=int(player_id),
                )
            return spot_id
        return graph.get_entity_spot(EntityId.create(int(player_id)))

    def _interaction_allows_actor(
        self, player_id: PlayerId, idef: InteractionDef
    ) -> bool:
        departed = bool(
            self._player_perception_policy is not None
            and self._player_perception_policy.is_departed(player_id)
        )
        plane = (
            InteractionActorPlane.DEPARTED
            if departed
            else InteractionActorPlane.LIVING
        )
        return idef.allows_actor_plane(plane)

    def set_cooldown_store(
        self,
        store: Optional[InteractionCooldownStore],
        *,
        minutes_per_tick: Optional[int] = None,
    ) -> None:
        """待ち時間の記録先を後付けで注入する (二段構築用)。"""
        self._cooldown_store = store
        self._minutes_per_tick = minutes_per_tick

    @staticmethod
    def _cooldown_ticks_of(idef: Any) -> int:
        raw = getattr(idef, "cooldown_ticks", 0) or 0
        return int(raw) if int(raw) > 0 else 0

    def remaining_cooldown_ticks(
        self,
        player_id: PlayerId,
        object_id: SpotObjectId,
        idef: Any,
        current_tick: Optional[WorldTick],
    ) -> int:
        """その人がその操作を使えるようになるまでの残り手番。使えるなら 0。"""
        cooldown = self._cooldown_ticks_of(idef)
        if not cooldown or self._cooldown_store is None or current_tick is None:
            return 0
        return self._cooldown_store.remaining_ticks(
            player_id,
            object_action_key(int(object_id), str(idef.cooldown_key)),
            cooldown_ticks=cooldown,
            current_tick=_tick_value(current_tick),
        )

    def cooldown_wait_hint(
        self,
        player_id: PlayerId,
        object_id: SpotObjectId,
        idef: Any,
        current_tick: Optional[WorldTick],
    ) -> str:
        """行に添える待ち時間の断り。待っていなければ空文字。

        行ごと消さない。消すと**自分の手段そのものを見失う** (#964 と同じ
        判断)。いつ使えるようになるかが書いてあれば、待つという次の手に繋がる。
        """
        remaining = self.remaining_cooldown_ticks(
            player_id, object_id, idef, current_tick
        )
        if remaining <= 0:
            return ""
        return f"あと{span_text(remaining, self._minutes_per_tick)}"

    def _interaction_def(self, interior: Any, object_id: SpotObjectId, action_name: str):
        obj = interior.get_object(object_id)
        if obj is None:
            return None
        for idef in obj.interactions:
            if idef.action_name == action_name:
                return idef
        return None

    def _refuse_if_still_waiting(
        self,
        player_id: PlayerId,
        object_id: SpotObjectId,
        action_name: str,
        interior: Any,
        current_tick: Optional[WorldTick],
    ) -> Any:
        """待ちが明けていなければ断る。明けていれば操作定義を返す。

        定義を返すのは、成功時の記録で**同じ定義を使う**ため。記録側で引き直すと
        効果適用後の世界を見てしまう。
        """
        idef = self._interaction_def(interior, object_id, action_name)
        if idef is None:
            return None
        remaining = self.remaining_cooldown_ticks(
            player_id, object_id, idef, current_tick
        )
        if remaining <= 0:
            return idef
        raise InteractionNotAllowedException(
            f"まだそれはできない。あと{span_text(remaining, self._minutes_per_tick)}。"
        )

    def _record_cooldown_start(
        self,
        player_id: PlayerId,
        object_id: SpotObjectId,
        action_name: str,
        action_def: Any,
        current_tick: Optional[WorldTick],
    ) -> None:
        """待ち時間の起点を控える。

        操作定義は拒否判定のときに引いたものを受け取る。ここで graph と interior
        を引き直すと、**効果で行為者が移動した世界を見てしまう** (テレポートを
        含む操作で起点が控えられなくなる)。
        """
        if self._cooldown_store is None or current_tick is None:
            return
        if action_def is None or not self._cooldown_ticks_of(action_def):
            return
        self._cooldown_store.record_success(
            player_id,
            object_action_key(int(object_id), str(action_def.cooldown_key)),
            _tick_value(current_tick),
        )

    def set_effective_lighting_resolver(self, resolver: Optional[Any]) -> None:
        """PR 3: 実効照明 resolver を後付け bind する (二段構築用)。"""
        self._effective_lighting_resolver = resolver

    def set_player_display_name_resolver(
        self, resolver: Optional[Callable[[PlayerId], str]]
    ) -> None:
        """player_display_name_resolver を後付けで注入する (二段構築用)。

        world_runtime のように scenario 由来の name map が interaction
        service の構築より後に確定するケースで使う。
        """
        self._player_display_name_resolver = resolver

    def set_time_of_day_phase_provider(self, provider: Optional[Any]) -> None:
        """PR4: 時間帯 provider を後付け bind する (runtime 順序依存解消用)。

        provider は `Callable[[], Optional[str]]` 想定。現在の phase 名
        ("morning"/"noon"/"evening"/"night" 等) を返す。
        """
        self._time_of_day_phase_provider = provider

    def set_weather_type_provider(self, provider: Optional[Any]) -> None:
        """PR4: 天候 provider を後付け bind する。

        provider は `Callable[[], Optional[str]]` 想定。現在の weather_type 名
        ("CLEAR"/"RAIN"/"STORM"/"FOG" 等) を返す。
        """
        self._weather_type_provider = provider

    def set_meeting_caller(
        self,
        caller: Optional[Callable[[PlayerId, str], Any]],
    ) -> None:
        """CALL_MEETING effect を実際の招集につなぐ callback を差す。

        誰を集めるか / フェーズをどう遷移させるかは application 層の判断な
        ので、domain の effect service には持たせない。runtime 組み立て時に
        第二引数で effect が宣言した trigger を渡す。
        """
        self._meeting_caller = caller

    def set_event_publisher(self, event_publisher: Any) -> None:
        """event_publisher を後付けで注入する (二段構築用)。

        通常は constructor で渡すのが望ましいが、world_runtime の
        ``create_world_runtime`` のように publisher が runtime
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
        spot_id = self._actor_spot(player_id, graph)

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

        # PR4: 時間帯 / 天候 condition 用 provider 呼び出し。
        # 例外は silent fallback で None にする (provider 不在扱いで条件が
        # 拒否される。シナリオ作家が provider を忘れた場合に surface する)。
        current_time_of_day_phase: Optional[str] = None
        if self._time_of_day_phase_provider is not None:
            try:
                current_time_of_day_phase = self._time_of_day_phase_provider()
            except Exception:
                current_time_of_day_phase = None
        current_weather_type: Optional[str] = None
        if self._weather_type_provider is not None:
            try:
                current_weather_type = self._weather_type_provider()
            except Exception:
                current_weather_type = None

        # PLAYERS_AT_SPOT (「N 人がその場に居ないと実行できない」) の判定材料。
        # graph の SpotPresence はプレイヤーのみを数える (monster は別辞書の
        # MonsterSpotPresence で管理される) ので、そのまま人数として渡せる。
        # ここで渡さないと domain 側の既定値 1 が使われ、何人集まっても
        # 常に「1 人」と判定される (PLAYERS_AT_SPOT が構造的に死ぬ)。
        spot_presence_count = len(graph.presence_at(spot_id).present_entity_ids)

        # PR-F: 看板 (WRITE_PLAYER_TEXT) が object.state に残す書き手名。
        # resolver 未注入 / 例外時は silent fallback ("プレイヤー({id})") にする。
        # 看板は書き手が分かることが価値の中心だが、resolver 未配線を例外で
        # 落とすとシナリオ側で看板を使わない限り無関係な interaction まで
        # 巻き込んで壊れるため、フォールバック名の劣化として扱う。
        acting_player_display_name: Optional[str] = None
        if self._player_display_name_resolver is not None:
            try:
                acting_player_display_name = self._player_display_name_resolver(player_id)
            except Exception:
                acting_player_display_name = None
        if not acting_player_display_name:
            acting_player_display_name = f"プレイヤー({int(player_id)})"

        # PR 3: SPOT_LIGHTING_IS の判定材料。resolver 未注入 / 解決失敗は
        # None のままにして、照明条件を成立させない。
        current_effective_lighting = None
        if self._effective_lighting_resolver is not None:
            current_effective_lighting = self._effective_lighting_resolver.resolve(
                spot_id
            )

        # 宣言した待ち時間がまだ明けていなければ、実行の前に断る。
        #
        # 読み込みは cooldown_ticks を受け取り、対人行為では効いていたのに、
        # ここだけ誰も見ていなかった。**作家の宣言が黙って捨てられていた。**
        action_def = self._refuse_if_still_waiting(
            player_id, object_id, action_name, interior, current_tick
        )
        if action_def is not None and not self._interaction_allows_actor(
            player_id, action_def
        ):
            raise InteractionNotAllowedException(
                "今の自分には、その操作を行うことができない。"
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
                acting_player_status=acting_player_status,
                current_time_of_day_phase=current_time_of_day_phase,
                current_weather_type=current_weather_type,
                spot_presence_count=spot_presence_count,
                acting_player_display_name=acting_player_display_name,
                current_effective_lighting=current_effective_lighting,
                current_spot_id=spot_id,
            )
        except InteractionNotAllowedException as exc:
            # 前提条件で拒否された。#356 後続: 旧コードは scenario JSON で
            # `on_failure_observation` を declared した interaction だけ他者
            # 観測が出ていたが、これだと「他人の失敗から学ぶ」シーンが
            # 著者の宣言漏れに依存して silent になる。失敗 reason を event
            # に乗せて常に emit し、formatter で prose を組む方針に変更。
            # 同 (actor, object, action, reason) の連発は dedup で抑える。
            self._maybe_emit_failure_observation(
                interior, object_id, action_name, entity_id, spot_id, graph,
                failure_reason=str(exc) if exc.args else "",
                current_tick=current_tick,
            )
            raise

        self._world_flag_state.replace_from_interaction(
            result.new_flags,
            context=WorldFlagMutationContext(
                source=WorldFlagMutationSource.SPOT_INTERACTION,
                actor_player_id=int(player_id),
            ),
        )

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

        # TELEPORT_ENTITY: 接続を辿らない移動を実際に適用する。
        # 以前はここに消費者が居らず、TeleportSpec を組み立てるだけで捨てて
        # いたため、シナリオ JSON に TELEPORT_ENTITY を書いても何も起きない
        # dead code だった (隠し通路・ベント・魔法陣が表現できない原因)。
        # graph の mutate なので passage と同じ区画に置き、下の
        # `graph.get_events()` 抽出より前に済ませる (Left / Entered を同じ
        # publish_all に乗せるため)。複数宣言された場合は順に適用し、最後の
        # 宛先が最終位置になる。
        # CALL_MEETING: 緊急招集ボタン。
        #
        # **配線が無いときは静かに捨てない。** TELEPORT_ENTITY はまさに
        # 「spec を組み立てるだけで消費者が居ない」状態で放置され、シナリオに
        # 書いても何も起きない dead code になっていた (上のコメント参照)。
        # 同じ轍を踏まないよう、宣言されたのに招集できない構成は例外で止める。
        meeting_messages: list[str] = []
        if result.meeting_call_triggers:
            caller = self._meeting_caller
            if caller is None:
                raise ApplicationException(
                    "CALL_MEETING が宣言されていますが、招集の配線 "
                    "(set_meeting_caller) がありません。"
                )
            for trigger in result.meeting_call_triggers:
                outcome = caller(player_id, trigger)
                # **拒否されたら黙って飲み込まない。** ボタンは持ち札 1 回 /
                # クールダウンつきなので、押しても始まらないことがある。
                # 何も返さないと「押した。以上」だけが残り、なぜ集まらな
                # かったのかが本人にも分からない (#860 で潰した
                # 「使えない候補を試し続ける」の再生産)。
                if outcome is not None and not getattr(outcome, "success", True):
                    refusal = getattr(outcome, "message", "")
                    if refusal:
                        meeting_messages.append(refusal)

        for teleport in result.teleport_specs:
            target_spot = SpotId.create(teleport.target_spot_id)
            if (
                self._player_perception_policy is not None
                and self._player_perception_policy.is_departed(player_id)
                and self._departed_position_store is not None
            ):
                self._departed_position_store.move(player_id, target_spot)
            else:
                graph.teleport_entity(entity_id, target_spot)

        # CHANGE_ATMOSPHERE: 明るさ・気温・危険度の変化を実際に適用する。
        # teleport と同じく、以前はここに消費者が居らず spec を捨てていたため
        # 「JSON に書いても照明が落ちない」dead code だった。lighting /
        # temperature の文字列は loader が enum 名として検証済みなので、ここでは
        # 変換して渡すだけでよい (未知の値は読み込み時に落ちている)。
        for atmosphere in result.atmosphere_update_specs:
            graph.update_spot_atmosphere(
                SpotId.create(atmosphere.spot_id),
                lighting=(
                    LightingEnum[atmosphere.lighting]
                    if atmosphere.lighting is not None
                    else None
                ),
                temperature=(
                    TemperatureEnum[atmosphere.temperature]
                    if atmosphere.temperature is not None
                    else None
                ),
                hazard_level=atmosphere.hazard_level,
                hazard_description=atmosphere.hazard_description,
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
        # Phase G #3 (silent failure fix): apply_damage で HP 0 になると
        # PlayerStatusAggregate は PlayerDownedEvent を内部に積む。これを
        # event_publisher.publish_all へ流さないと PlayerDownedOutcomeHandler
        # が走らず、接触ダメージで死んでも DEAD outcome が確定しない silent
        # 破綻になっていた。aggregate の events を回収して後段の publish_all
        # で他 event と合わせて流す。
        # イベントは save より先に回収 + clear する (needs_decay / status_effects と
        # 同じ「publisher ガード内で clear してから save」)。save→clear の逆順だと
        # PlayerDownedEvent を持ったまま集約が永続化され、後続の
        # find→get_events→publish で陳腐化イベントが再放出される (tend_to_player の
        # 復帰イベント再放出と同型のバグ)。repo 境界の drain
        # (in_memory_repository_base._clone) と二重の防御。event_publisher が None の
        # ときは clear せず save する (canonical は _clone が drain する)。
        status_events_from_damage: list = []
        if result.damage_specs and self._player_status_repository is not None:
            status = self._player_status_repository.find_by_id(player_id)
            if status is not None:
                for spec in result.damage_specs:
                    if spec.damage <= 0:
                        continue  # 0 ダメージは no-op
                    status.apply_damage(spec.damage)
                if self._event_publisher is not None:
                    status_events_from_damage = list(status.get_events())
                    status.clear_events()
                self._player_status_repository.save(status)

        # PR #2 状態異常: APPLY_STATUS_EFFECT で発生した StatusEffectSpec を
        # PlayerStatusAggregate.add_status_effect に渡す。expiry_tick は
        # current_tick + duration_ticks で計算する。effect は tick 毎に
        # StatusEffectsTickStageService が継続適用 / 期限切れ掃除する。
        if result.status_effect_specs and self._player_status_repository is not None:
            from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
            from ai_rpg_world.domain.combat.value_object.status_effect import (
                StatusEffect,
            )
            from ai_rpg_world.domain.common.value_object import WorldTick as _WT
            status = self._player_status_repository.find_by_id(player_id)
            if status is not None:
                effective_tick = current_tick or _WT(0)
                for spec in result.status_effect_specs:
                    try:
                        effect_type = StatusEffectType(spec.effect_type_name)
                    except ValueError:
                        import logging
                        logging.getLogger(__name__).warning(
                            "Unknown StatusEffectType %r in status_effect_spec, "
                            "skipping (player_id=%s)",
                            spec.effect_type_name, int(player_id),
                        )
                        continue
                    expiry_tick = _WT(effective_tick.value + max(0, spec.duration_ticks))
                    status.add_status_effect(StatusEffect(
                        effect_type=effect_type,
                        value=spec.value,
                        expiry_tick=expiry_tick,
                    ))
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
                        # silent failure fix: 未知 NeedType は作家ミスを示す。
                        # 黙って捨てるとシナリオ作者が「回復が効かない」と
                        # 気づくまで分からないので warning log で surface する。
                        import logging
                        logging.getLogger(__name__).warning(
                            "Unknown NeedType %r in satisfy_need_spec, "
                            "skipping (player_id=%s, amount=%d)",
                            spec.need_type_name, int(player_id), spec.amount,
                        )
                self._player_status_repository.save(status)

        # aggregate が貯めたイベント (ConnectionStateChanged 等) を抽出
        graph_events = list(graph.get_events())
        graph.clear_events()

        self._spot_graph_repository.save(graph)

        # SpotObjectInteractedEvent を明示的に作成して publish
        if self._event_publisher is not None:
            # Phase G #1: 元の interior (mutate 前) を引き直して InteractionDef
            # の witness_policy を回収する。result.new_interior は CHANGE_OBJECT_STATE
            # 等で書き換わっている可能性があるが、interactions array 自体は
            # 同 def を参照しているので default SAME_SPOT は安全。万一見つから
            # なければ default フォールバック。
            from ai_rpg_world.domain.world_graph.enum.witness_policy import (
                WitnessPolicy as _WP,
            )
            witness_policy = _WP.SAME_SPOT
            witness_observation_message = ""
            new_obj = result.new_interior.get_object(object_id)
            if new_obj is not None:
                for idef in new_obj.interactions:
                    if idef.action_name == action_name:
                        witness_policy = idef.witness_policy
                        witness_observation_message = idef.witness_observation_message or ""
                        break
            interacted_event = SpotObjectInteractedEvent.create(
                aggregate_id=graph.graph_id,
                aggregate_type="SpotGraphAggregate",
                entity_id=entity_id,
                spot_id=spot_id,
                object_id=object_id,
                action_name=action_name,
                result_message="；".join(result.messages) if result.messages else "",
                action_display_label=result.action_display_label,
                witness_observation_message=witness_observation_message,
                witness_policy=witness_policy,
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
            # Phase G #3 (silent failure fix): damage 経由で aggregate が積んだ
            # PlayerDownedEvent も同 publish_all に乗せて、E-3a の
            # PlayerDownedOutcomeHandler へ届ける。空 list の場合は no-op。
            self._event_publisher.publish_all(
                [*graph_events, interacted_event, *public_events, *status_events_from_damage]
            )

        # 成功したときだけ起点を更新する。**適用と観測配信がすべて終わったあと**
        # に置く。前提条件で弾かれた場合だけでなく、効果計算より後の保存や配信で
        # 落ちた場合にも記録してはいけない。空振りで待たされると「前提条件を
        # 試すことが罰」になる (対人行為と同じ判断)。
        #
        # 最初は flag 反映の直前に置いていて、後段で落ちた操作にも待ち時間が
        # 付いていた (codex の指摘)。
        self._record_cooldown_start(
            player_id, object_id, action_name, action_def, current_tick
        )

        return SpotInteractionResultDto(
            messages=(*result.messages, *meeting_messages),
            action_display_label=result.action_display_label,
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
                # TELEPORT_ENTITY の entity 移動は `graph.teleport_entity` で
                # 適用済み。移動の観測は EntityLeftSpotEvent /
                # EntityEnteredSpotEvent が出発・到着の両スポットへ配るので、
                # ここで SpotPublicEffectObservedEvent を重ねると同じ移動が
                # 二重に観測される。よって発火しない (visibility が
                # PUBLIC_OBSERVABLE でも同じ)。
                _logger.debug(
                    "TELEPORT summary is delivered via EntityLeft/EnteredSpotEvent; "
                    "skipping duplicate observation event"
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
        *,
        failure_reason: str = "",
        current_tick: Optional[WorldTick] = None,
    ) -> None:
        """失敗観測 event を publish する (他者の失敗から学ぶ用)。

        旧仕様は `InteractionDef.on_failure_observation` が宣言されている時
        だけ event を出していた。新仕様は **常に emit を試みる**:

        - 宣言された `on_failure_observation` があればそれを override として渡す
          (= シナリオ著者の自由文を尊重)
        - 無ければ `failure_reason` (= 例外メッセージ) を event に乗せ、
          formatter が「{actor}が{object}の{action}を試みたが、{reason}」を
          組む
        - 両方無いケース (本来は起きない) は何もしない

        dedup: 同 (actor, object, action, reason) が
        `_failure_observation_dedup_window` (デフォルト 24 tick) 以内に
        2 度目に来たら emit を skip。LLM の retry loop で同じ失敗が連発
        するスパムを抑える (`current_tick` が None なら dedup 無し)。
        """
        if self._event_publisher is None:
            return
        obj = interior.get_object(object_id)
        if obj is None:
            return
        idef = next(
            (i for i in obj.interactions if i.action_name == action_name), None,
        )
        # **役割で弾かれた失敗は、目撃者に配らない。**
        #
        # 理由の文 (「その手順は自分の担当ではない」) が、その人の役割を
        # 明かしてしまう。表示をラベルに直しても理由は残るので、観測ごと
        # 落とす。本人にはツール結果として返るので、学習材料は失われない。
        # #905 で候補一覧に置いたのと同じ原則。
        actor_state = {}
        if self._player_status_repository is not None:
            from ai_rpg_world.domain.player.value_object.player_id import (
                PlayerId as _PlayerId,
            )
            status = self._player_status_repository.find_by_id(
                _PlayerId(int(entity_id))
            )
            actor_state = dict(getattr(status, "state", {}) or {}) if status else {}
        if idef is not None and _hidden_precondition_failed(idef, actor_state):
            return
        # シナリオ著者が override を宣言している場合は失敗 reason より優先する
        override = idef.on_failure_observation if idef is not None else None
        # 両方とも空ならそもそも観測 prose を組めないので silent (legacy fallback)
        if not override and not failure_reason:
            return
        # dedup throttle: 同じ失敗の連発を 1 window あたり 1 件に絞る
        if current_tick is not None:
            key = (
                int(entity_id),
                int(object_id),
                action_name,
                failure_reason or (override or ""),
            )
            tick_int = (
                current_tick.value
                if hasattr(current_tick, "value")
                else int(current_tick)
            )
            last = self._failure_observation_last_tick.get(key)
            if last is not None and (tick_int - last) < self._failure_observation_dedup_window:
                return
            self._failure_observation_last_tick[key] = tick_int
            # TTL eviction: window を 2x 超えた古いエントリを掃除して dict
            # の無限増加を防ぐ (long-run セッション対策、code-review HIGH)。
            # 毎回全走査するが key 数は通常 O(actors × objects) で小さい。
            ttl_cutoff = tick_int - 2 * self._failure_observation_dedup_window
            if ttl_cutoff > 0:
                self._failure_observation_last_tick = {
                    k: v
                    for k, v in self._failure_observation_last_tick.items()
                    if v > ttl_cutoff
                }
        failed_event = SpotObjectInteractionFailedEvent.create(
            aggregate_id=graph.graph_id,
            aggregate_type="SpotGraphAggregate",
            entity_id=entity_id,
            spot_id=spot_id,
            object_id=object_id,
            action_name=action_name,
            observation_message=override or "",
            failure_reason=failure_reason if not override else "",
                    display_label=(idef.display_label if idef is not None else ""),
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
