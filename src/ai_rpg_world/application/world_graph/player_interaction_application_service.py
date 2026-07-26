"""同じ場所にいるプレイヤーを対象にした interaction を実行する。

物体への interaction (``SpotInteractionApplicationService``) と対になる。
対象が物体ではなく人であることを除けば、前提条件の評価も効果の適用も同じ
仕組みを使う — 条件は ``SpotInteractionService.can_interact``、効果は
``WorldGraphEffectService.apply_effects``。前提条件の判定を対人用に書き直す
と 5 系統目の独立実装になり、条件が増えるたびに追従漏れが起きる。

定義はシナリオ直下の ``player_interactions`` に 1 回だけ書く。物体に紐付ける
と同じ行為を場所ごとに複製することになり、場所の制約は前提条件で書けば足りる
(docs/memory_system/interpersonal_interaction_design.md §3.2)。

**本サービスの守備範囲はアイテムの授受まで**。ダメージ / 状態異常 / 欲求への
対人適用は、対象の ``PlayerDownedEvent`` を回収しないとキル判定が確定しない
という別の問題 (設計 doc H-1) を抱えるので、別の PR で扱う。宣言だけできて
効かない状態を作らないよう、未配線の効果は loader が起動時に弾く。
"""

from __future__ import annotations

import logging
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
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
    InteractionNotFoundException,
)
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    PlayerInteractedWithPlayerEvent,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
    SpotInteractionService,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlayerInteractionResultDto:
    """対人 interaction の実行結果。"""

    action_name: str
    actor_player_id: int
    target_player_id: int
    messages: Tuple[str, ...]
    # 行為者が受け取った / 失った item spec id (観測や trace 用)
    actor_granted_spec_ids: Tuple[int, ...] = ()
    actor_removed_spec_ids: Tuple[int, ...] = ()
    # 対象が受け取った / 失った item spec id
    target_granted_spec_ids: Tuple[int, ...] = ()
    target_removed_spec_ids: Tuple[int, ...] = ()


class PlayerInteractionApplicationService:
    """シナリオ直下に宣言された対人 interaction を実行する。"""

    def __init__(
        self,
        *,
        spot_graph_repository: ISpotGraphRepository,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
        item_spec_repository: ItemSpecRepository,
        player_status_repository: Optional[PlayerStatusRepository],
        world_flag_state: MutableWorldFlagState,
        player_interactions: Tuple[InteractionDef, ...],
        interaction_service: Optional[SpotInteractionService] = None,
        effect_service: Optional[WorldGraphEffectService] = None,
        event_publisher: Optional[Any] = None,
        # PR 3: 場所・時間・天候の前提条件を評価するための現在値。いずれも
        # 未注入なら該当条件は成立しない (silent pass させない)。物体経路
        # (SpotInteractionApplicationService) と揃える。
        effective_lighting_resolver: Optional[Any] = None,
        time_of_day_phase_provider: Optional[Any] = None,
        weather_type_provider: Optional[Any] = None,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        self._item_spec_repository = item_spec_repository
        self._player_status_repository = player_status_repository
        self._world_flag_state = world_flag_state
        self._effect_service = effect_service or WorldGraphEffectService()
        self._interaction = interaction_service or SpotInteractionService(
            self._effect_service
        )
        self._event_publisher = event_publisher
        self._effective_lighting_resolver = effective_lighting_resolver
        self._time_of_day_phase_provider = time_of_day_phase_provider
        self._weather_type_provider = weather_type_provider
        self._by_action_name: Dict[str, InteractionDef] = {
            idef.action_name: idef for idef in player_interactions
        }

    def set_effective_lighting_resolver(self, resolver: Optional[Any]) -> None:
        """実効照明 resolver を後付けで注入する (二段構築用)。"""
        self._effective_lighting_resolver = resolver

    def set_time_of_day_phase_provider(self, provider: Optional[Any]) -> None:
        """時間帯 provider を後付けで注入する (二段構築用)。"""
        self._time_of_day_phase_provider = provider

    def set_weather_type_provider(self, provider: Optional[Any]) -> None:
        """天候 provider を後付けで注入する (二段構築用)。"""
        self._weather_type_provider = provider

    def _current_value_from(self, provider: Optional[Any]) -> Optional[str]:
        """provider から現在値を取る。未注入 / 失敗なら None。

        None は「その条件を成立させない」に倒れる。物体経路と同じ判断で、
        provider の配線漏れを「常に失敗する」形で表に出す。
        """
        if provider is None:
            return None
        try:
            return provider()
        except Exception:
            return None

    def set_event_publisher(self, event_publisher: Any) -> None:
        """event_publisher を後付けで注入する (二段構築用)。

        publisher は runtime 本体に依存して構築されるので、本 service より
        後になる。``SpotInteractionApplicationService`` と同じ約束。
        """
        self._event_publisher = event_publisher

    def available_action_names(self) -> Tuple[str, ...]:
        """宣言されている対人 action 名を宣言順で返す (prompt の候補表示用)。"""
        return tuple(self._by_action_name.keys())

    def execute(
        self,
        actor_player_id: PlayerId,
        target_player_id: PlayerId,
        action_name: str,
        *,
        interaction_parameters: Optional[Dict[str, Any]] = None,
        current_tick: Optional[WorldTick] = None,
    ) -> PlayerInteractionResultDto:
        """対人 interaction を 1 件実行する。

        Raises:
            InteractionNotFoundException: その action がシナリオに無い
            InteractionNotAllowedException: 前提条件を満たさない
            ApplicationException: 同じ場所にいない / 自分自身を対象にした等
        """
        idef = self._by_action_name.get(action_name)
        if idef is None:
            raise InteractionNotFoundException(
                f"対人 action が定義されていません: {action_name}"
            )
        if int(actor_player_id) == int(target_player_id):
            # 自分を対象にした対人行為は、成立しても意味が無いうえに
            # 「対象から奪って自分に渡す」が no-op になって成功として返る。
            raise ApplicationException(
                "自分自身を対象にはできません。",
                player_id=int(actor_player_id),
            )

        graph = self._spot_graph_repository.find_graph()
        actor_spot = graph.get_entity_spot(EntityId.create(int(actor_player_id)))
        target_spot = graph.get_entity_spot(EntityId.create(int(target_player_id)))
        if actor_spot != target_spot:
            raise ApplicationException(
                "相手が同じ場所にいません。",
                player_id=int(actor_player_id),
            )

        actor_inv = self._require_inventory(actor_player_id)
        target_inv = self._require_inventory(target_player_id)

        actor_status = None
        target_status = None
        if self._player_status_repository is not None:
            actor_status = self._player_status_repository.find_by_id(actor_player_id)
            target_status = self._player_status_repository.find_by_id(target_player_id)

        # 効果を当てる前に対象の状態を控える。適用後に問い合わせると、
        # 昏倒させた一撃そのものが「倒れている間にされたこと」に化ける。
        target_was_down = bool(getattr(target_status, "is_down", False))

        owned = collect_owned_item_spec_ids_from_inventory(
            actor_inv, self._item_repository
        )
        owned_counts = count_owned_item_instances_by_spec(
            actor_inv, self._item_repository
        )
        target_owned = collect_owned_item_spec_ids_from_inventory(
            target_inv, self._item_repository
        )
        spot_presence_count = len(graph.presence_at(actor_spot).present_entity_ids)

        # LLM は「太い流木を奪う」のように**名前**で品目を指す (倒れた相手の
        # 持ち物は prompt に出ている: PR #824)。domain 側は spec id しか扱わ
        # ないので、名前 → spec id の解決はここで済ませて
        # ``interaction_parameters`` に入れておく。見つからないときは入れない
        # ままにして、``TARGET_HAS_ITEM`` に「相手はそれを持っていない」と
        # 言わせる (ここで例外にすると LLM が学習できない失敗になる)。
        resolved_parameters = self._with_resolved_item_spec_id(
            interaction_parameters, target_inv
        )

        ok, reason = self._interaction.can_interact(
            idef,
            None,
            owned,
            self._world_flag_state.as_frozen_set(),
            spot_presence_count=spot_presence_count,
            interaction_parameters=resolved_parameters,
            owned_item_spec_counts=owned_counts,
            acting_player_status=actor_status,
            target_player_status=target_status,
            target_owned_item_spec_ids=target_owned,
            current_tick=current_tick,
            current_time_of_day_phase=self._current_value_from(
                self._time_of_day_phase_provider
            ),
            current_weather_type=self._current_value_from(
                self._weather_type_provider
            ),
            current_effective_lighting=(
                self._effective_lighting_resolver.resolve(actor_spot)
                if self._effective_lighting_resolver is not None
                else None
            ),
            current_spot_id=actor_spot,
        )
        if not ok:
            raise InteractionNotAllowedException(reason or "この行為はできない")

        result = self._effect_service.apply_effects(
            # 対人 interaction は物体を触らないので、空の interior を渡す。
            # effect 側が interior を書き換えても捨てる (下で使わない)。
            interior=SpotInterior((), (), (), ()),
            acting_object=None,
            effects=idef.effects,
            world_flags=self._world_flag_state.as_frozen_set(),
            current_tick=current_tick,
            acting_player_status=actor_status,
            target_player_status=target_status,
            interaction_parameters=resolved_parameters,
        )

        self._world_flag_state.replace_from_interaction(result.new_flags)

        # 受け取る側に空きがあるか、**何も動かす前に**確かめる。
        #
        # PlayerInventoryAggregate.acquire_item は満杯のとき黙って捨てる
        # (overflow event を積むだけで例外にしない)。先に取り上げてから渡すと
        # 「対象からは消えて行為者には入らない」= アイテムが世界から消滅し、
        # しかも成功として返るので誰も気づけない。
        self._require_free_slots(
            actor_player_id, len(result.item_spec_ids_to_grant), "あなた"
        )
        self._require_free_slots(
            target_player_id, len(result.target_item_spec_ids_to_grant), "相手"
        )

        # 先に対象から取り上げ、次に行為者へ渡す。順序を逆にすると、対象が
        # 持っていなかった場合に「行為者は受け取ったが対象は失っていない」
        # という複製が一瞬成立してしまう。
        self._remove_from(
            target_player_id, result.target_item_spec_ids_to_remove, "対象"
        )
        self._remove_from(
            actor_player_id, result.item_spec_ids_to_remove, "行為者"
        )
        self._grant_to(target_player_id, result.target_item_spec_ids_to_grant)
        self._grant_to(actor_player_id, result.item_spec_ids_to_grant)

        if result.acting_player_state_changed and actor_status is not None:
            self._player_status_repository.save(actor_status)

        # 対象へのダメージ。H-1 (設計 doc) の罠がここにある。
        #
        # HP 0 になると対象の集約が PlayerDownedEvent を内部に積む。これを
        # publish しないと PlayerDownedOutcomeHandler が走らず、**倒したのに
        # DEAD outcome が確定しない**。倒れた本人も蘇生猶予に入らないので、
        # 実験の勝敗判定が静かに壊れる。
        #
        # 順序は物体経路 (Phase G #3) と同じ「publisher ガード内で drain →
        # clear → save」。save が先だと event を持ったまま永続化され、後続の
        # find→get_events で陳腐化イベントが二重に流れる。
        status_events_from_damage: list = []
        # 行為者自身へのダメージ (反動 / 代償)。target=ACTOR の APPLY_DAMAGE を
        # 受け付けておいて何も起こさないと、作者は書いたつもりのまま気付けない。
        if result.damage_specs and actor_status is not None:
            for spec in result.damage_specs:
                if spec.damage <= 0:
                    continue
                actor_status.apply_damage(spec.damage)
            if self._event_publisher is not None:
                status_events_from_damage.extend(actor_status.get_events())
                actor_status.clear_events()
            self._player_status_repository.save(actor_status)
        if result.target_damage_specs and target_status is not None:
            for spec in result.target_damage_specs:
                if spec.damage <= 0:
                    continue
                target_status.apply_damage(
                    spec.damage, killer_player_id=actor_player_id
                )
            if self._event_publisher is not None:
                status_events_from_damage.extend(target_status.get_events())
                target_status.clear_events()
            self._player_status_repository.save(target_status)

        # 観測を伴わない対人行為は作らない。state だけ変わって誰にも何も
        # 見えないと、被害者は次のターンに持ち物が消えていることに気づく
        # だけになり、trace からも効果を確認できない。
        #
        # publisher 未注入は配線漏れだが、ここで落とすと実験そのものが
        # 止まる。警告を残して行為自体は成立させる (観測が消えたことは
        # 警告で追える)。
        if self._event_publisher is None:
            _logger.warning(
                "PlayerInteractionApplicationService に event_publisher が "
                "注入されていないため、対人行為 %r の観測が誰にも届きません",
                action_name,
            )
        else:
            self._event_publisher.publish_all([
                *status_events_from_damage,
                PlayerInteractedWithPlayerEvent.create(
                    aggregate_id=graph.graph_id,
                    aggregate_type="SpotGraphAggregate",
                    entity_id=EntityId.create(int(actor_player_id)),
                    target_entity_id=EntityId.create(int(target_player_id)),
                    spot_id=actor_spot,
                    action_name=action_name,
                    result_message="; ".join(result.messages),
                    action_display_label=idef.display_label or "",
                    witness_observation_message=(
                        idef.witness_observation_message or ""
                    ),
                    witness_policy=idef.witness_policy,
                    target_was_down=target_was_down,
                )
            ])

        return PlayerInteractionResultDto(
            action_name=action_name,
            actor_player_id=int(actor_player_id),
            target_player_id=int(target_player_id),
            messages=tuple(result.messages),
            actor_granted_spec_ids=tuple(
                s.value for s in result.item_spec_ids_to_grant
            ),
            actor_removed_spec_ids=tuple(
                s.value for s in result.item_spec_ids_to_remove
            ),
            target_granted_spec_ids=tuple(
                s.value for s in result.target_item_spec_ids_to_grant
            ),
            target_removed_spec_ids=tuple(
                s.value for s in result.target_item_spec_ids_to_remove
            ),
        )

    #: LLM が奪う品目を名指しするときに使う ``interaction_parameters`` のキー。
    #: 解決後の spec id は ``ITEM_SPEC_ID_KEY`` に入れ、シナリオ側の
    #: ``item_spec_id_parameter`` / ``item_spec_id_parameter_key`` はこちらを指す。
    ITEM_NAME_KEY = "item"
    ITEM_SPEC_ID_KEY = "item_spec_id"

    def _with_resolved_item_spec_id(
        self,
        interaction_parameters: Optional[Dict[str, Any]],
        target_inventory,
    ) -> Optional[Dict[str, Any]]:
        """``parameters["item"]`` (品目名) を対象の所持から spec id へ解決する。

        見つからなければ何も足さない。「相手はその名前のものを持っていない」
        は普通に起きる状況なので、ここで例外にすると LLM が学習できない失敗に
        なる。条件 (``TARGET_HAS_ITEM``) 側が不成立として言葉で返す。

        既に ``item_spec_id`` が入っている呼び出し (テストや将来の別経路) は
        そのまま尊重して上書きしない。
        """
        if not interaction_parameters:
            return interaction_parameters
        if self.ITEM_SPEC_ID_KEY in interaction_parameters:
            return interaction_parameters
        raw_name = interaction_parameters.get(self.ITEM_NAME_KEY)
        if not isinstance(raw_name, str) or not raw_name.strip():
            return interaction_parameters
        spec_id = self._find_spec_id_by_name(target_inventory, raw_name.strip())
        if spec_id is None:
            return interaction_parameters
        return {**interaction_parameters, self.ITEM_SPEC_ID_KEY: spec_id.value}

    def _find_spec_id_by_name(self, inventory, name: str):
        """対象の所持品から表示名が一致する item spec id を引く。

        同名の別 spec が複数あるときは、どれか 1 つを選ばずに例外で止める。
        ``collect_owned_item_spec_ids_from_inventory`` が返すのは frozenset で
        反復順が保証されないため、素朴に最初の一致を返すと **実行ごとに違う
        物を奪う**。対象名の解決 (``resolve_target``) で種別横断の同名衝突を
        拒否したのと同じ理由で、ここでも黙って選ばない。
        """
        matches = [
            spec_id
            for spec_id in collect_owned_item_spec_ids_from_inventory(
                inventory, self._item_repository
            )
            if self._spec_name(spec_id) == name
        ]
        if len(matches) > 1:
            raise InteractionNotAllowedException(
                f"「{name}」に当てはまるものが相手の持ち物に複数ある。"
                "どれを指すのか決められないので、別の物を指定すること。"
            )
        return matches[0] if matches else None

    def _spec_name(self, spec_id) -> Optional[str]:
        spec = self._item_spec_repository.find_by_id(spec_id)
        return getattr(spec, "name", None) if spec is not None else None

    def _require_free_slots(
        self, player_id: PlayerId, needed: int, who: str
    ) -> None:
        """受け取りに必要な空きスロットが無ければ、前提条件の不成立で止める。

        ``InteractionNotAllowedException`` を使うのは、これが配線の壊れでは
        なく**普通に起きる状況**だからである。executor が
        ``INTERACTION_PRECONDITION_FAILED`` に変換するので、LLM は「先に何かを
        置いてから奪う」という次の手を選べる。
        """
        if needed <= 0:
            return
        from ai_rpg_world.domain.player.value_object.slot_id import SlotId

        inv = self._require_inventory(player_id)
        free = sum(
            1
            for i in range(inv.max_slots)
            if inv.get_item_instance_id_by_slot(SlotId(i)) is None
        )
        if free < needed:
            raise InteractionNotAllowedException(
                f"{who}の手が塞がっている (空き {free} / 必要 {needed})。"
                "先に何かを置くか使うかしてから試すこと。"
            )

    def _require_inventory(self, player_id: PlayerId):
        inv = self._player_inventory_repository.find_by_id(player_id)
        if inv is None:
            raise ApplicationException(
                f"インベントリが見つかりません: {player_id}",
                player_id=int(player_id),
            )
        return inv

    def _grant_to(self, player_id: PlayerId, spec_ids) -> None:
        if not spec_ids:
            return
        grant_item_specs_to_inventory(
            player_id,
            tuple(spec_ids),
            self._item_repository,
            self._item_spec_repository,
            self._player_inventory_repository,
        )

    def _remove_from(self, player_id: PlayerId, spec_ids, who: str) -> None:
        """指定プレイヤーの所持品から spec_ids を 1 個ずつ取り除く。

        取り除けないときは黙って飛ばさず例外にする。前提条件で所持を確認した
        うえで来ているので、ここで足りないのは何かが壊れている状態であり、
        飛ばすと「奪えたはずが何も起きていないのに成功と返る」ことになる。
        """
        if not spec_ids:
            return
        inv = self._require_inventory(player_id)
        for spec_id in spec_ids:
            if not remove_one_item_of_spec_from_inventory(
                inv, spec_id, self._item_repository
            ):
                raise ApplicationException(
                    f"{who}の所持品から取り除けませんでした "
                    f"(spec_id={spec_id.value}); 前提条件との不一致",
                    player_id=int(player_id),
                )
        self._player_inventory_repository.save(inv)
