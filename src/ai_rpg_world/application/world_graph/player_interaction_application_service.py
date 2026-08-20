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
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional, Tuple

from ai_rpg_world.application.common.exceptions import ApplicationException
from ai_rpg_world.application.player.services.player_life_query import PlayerLifeQuery
from ai_rpg_world.application.player.services.player_perception_policy import (
    PlayerPerceptionPolicy,
)
from ai_rpg_world.application.player.services.fallen_body_registry import (
    FallenBodyRegistry,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
    plan_item_removals_from_inventory,
    remove_items_of_specs_from_inventory,
)
from ai_rpg_world.application.world_graph.interaction_wait_text import span_text
from ai_rpg_world.application.world_graph.declared_observation_message import (
    declared_observation_message_for_lighting,
)
from ai_rpg_world.application.world_graph.world_flag_state import (
    MutableWorldFlagState,
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.application.world_graph.interaction_actor_plane import (
    actor_plane_for,
    actor_plane_refusal_message,
)
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
from ai_rpg_world.domain.player.service.actionable_target import (
    TargetRequirement,
    validate_actionable_target,
)
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionActorPlaneNotAllowedException,
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
from ai_rpg_world.application.llm.services.world_vocabulary import (
    lighting_display,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.application.world_graph.hidden_interaction_filter import (
    visible_action_names_for_state,
)
from ai_rpg_world.application.world_graph.interaction_condition_hint_text import (
    declarative_condition_hints,
    format_action_display_with_hints,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphInteractionEntry,
)
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import (
    InteractionEffectTypeEnum,
)
from ai_rpg_world.domain.world_graph.enum.witness_policy import WitnessPolicy
from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope import CommandContext
    from ai_rpg_world.application.common.command_scope_factory import (
        CommandScopeFactoryPort,
    )
    from ai_rpg_world.application.world_graph.interaction_command_repository_provider import (
        InteractionCommandRepositoryProviderPort,
    )

_logger = logging.getLogger(__name__)

#: 実効照明を見る前提条件。行のヒントは実行時と同じ極性で読む必要がある。
_LIGHTING_CONDITION_TYPES = (
    InteractionConditionTypeEnum.SPOT_LIGHTING_IS,
    InteractionConditionTypeEnum.SPOT_LIGHTING_IS_NOT,
)


def _actor_meets_own_state_conditions(
    idef: "InteractionDef", actor_state: Mapping[str, Any]
) -> bool:
    """行動者自身の state 条件をすべて満たすか。

    ``PLAYER_STATE_IS`` **だけ**を見る。この条件が参照するのは行動者自身の
    自由 state で、本人が知っている情報しか使わない。

    ``TARGET_PLAYER_STATE_IS`` をここで扱ってはいけない。対象の秘匿された
    役割でラベルの有無が変わり、**誰がクルーかが行動一覧から読める**。

    宣言に required_state が無いものは判定材料が無いので満たさない扱いに
    する。黙って通すと、書き損じた条件が効かないまま静かに素通りする。
    """
    for cond in idef.preconditions:
        if cond.condition_type is not InteractionConditionTypeEnum.PLAYER_STATE_IS:
            continue
        required = cond.required_state
        if not required:
            return False
        for key, value in required.items():
            if actor_state.get(key) != value:
                return False
    return True


def _known_ally_meets_target_role_conditions(
    idef: "InteractionDef", actor_state: Optional[Mapping[str, Any]]
) -> bool:
    """既知の相方が、対象 role 条件を満たすはずかを公開済み情報だけで判定する。

    「同じ側」と知っているなら、対象の role は行動者自身と同じであることも
    本人には既知である。対象の state は受け取らず、行動者自身の ``role`` と
    宣言値だけを比べる。他の ``required_state`` は相方関係から分からないため
    候補の絞り込みには使わない。
    """
    if actor_state is None or "role" not in actor_state:
        return True
    for cond in idef.preconditions:
        if (
            cond.condition_type
            is not InteractionConditionTypeEnum.TARGET_PLAYER_STATE_IS
        ):
            continue
        required = cond.required_state or {}
        if "role" in required and required["role"] != actor_state["role"]:
            return False
    return True


def _target_requirement(idef: "InteractionDef") -> TargetRequirement:
    """宣言された対象条件を、候補表示と実行時で同じ要求へ畳み込む。

    ``TARGET_PLAYER_IS_INCAPACITATED`` を持つ操作だけが倒れた相手を要求する。
    持たない対人操作は起きて動ける相手を要求する。候補表示だけでこの区別を
    行うと、同じ wave の先着が対象を倒したあとでも、後着が古い候補をそのまま
    実行できてしまうため、適用時にも同じ宣言から判断する。
    """
    return (
        TargetRequirement.INCAPACITATED
        if any(
            cond.condition_type
            is InteractionConditionTypeEnum.TARGET_PLAYER_IS_INCAPACITATED
            for cond in idef.preconditions
        )
        else TargetRequirement.ACTIVE
    )


@dataclass(frozen=True)
class PlayerInteractionResultDto:
    """対人 interaction の実行結果。"""

    action_name: str
    actor_player_id: int
    target_player_id: int
    messages: Tuple[str, ...]
    action_display_label: str
    # 行為者が受け取った / 失った item spec id (観測や trace 用)
    actor_granted_spec_ids: Tuple[int, ...] = ()
    actor_removed_spec_ids: Tuple[int, ...] = ()
    # 対象が受け取った / 失った item spec id
    target_granted_spec_ids: Tuple[int, ...] = ()
    target_removed_spec_ids: Tuple[int, ...] = ()


class _CommandContextEventPublisher:
    """既存publish_all入口をCommandContextのイベント収集へ適合させる。"""

    def __init__(self, context: "CommandContext") -> None:
        self._context = context

    def publish_all(self, events: Any) -> None:
        self._context.collect_all(events)


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
        player_life_query: PlayerLifeQuery,
        fallen_body_registry: FallenBodyRegistry,
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
        # 対人行為の再使用間隔。未注入なら間隔を課さない (既存の組み立て
        # 経路を壊さないため)。本番経路は world_runtime が必ず渡す。
        cooldown_store: Optional[Any] = None,
        # 残り tick をヒントに出すために現在 tick が要る。未注入なら出さない。
        current_tick_provider: Optional[Any] = None,
        # 残り時間を世界の単位で書くための換算。未注入なら「手番 N 回ぶん」
        # と書く。**tick は出さない** (#892)。
        minutes_per_tick: Optional[int] = None,
        player_perception_policy: Optional[PlayerPerceptionPolicy] = None,
        interaction_command_scope_factory: Optional[
            "CommandScopeFactoryPort[InteractionCommandRepositoryProviderPort]"
        ] = None,
        overflow_sink: Any = None,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository
        self._item_spec_repository = item_spec_repository
        self._player_status_repository = player_status_repository
        self._player_life_query = player_life_query
        self._fallen_body_registry = fallen_body_registry
        self._world_flag_state = world_flag_state
        self._effect_service = effect_service or WorldGraphEffectService()
        self._interaction = interaction_service or SpotInteractionService(
            self._effect_service
        )
        self._event_publisher = event_publisher
        self._cooldown_store = cooldown_store
        self._current_tick_provider = current_tick_provider
        self._minutes_per_tick = minutes_per_tick
        self._effective_lighting_resolver = effective_lighting_resolver
        self._time_of_day_phase_provider = time_of_day_phase_provider
        self._weather_type_provider = weather_type_provider
        self._player_perception_policy = player_perception_policy
        self._interaction_command_scope_factory = interaction_command_scope_factory
        self._by_action_name: Dict[str, InteractionDef] = {
            idef.action_name: idef for idef in player_interactions
        }
        self._overflow_sink = overflow_sink

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

    def set_command_scope_factory(
        self,
        factory: Optional[
            "CommandScopeFactoryPort[InteractionCommandRepositoryProviderPort]"
        ],
    ) -> None:
        """対人interactionを確定するCommandScopeを後付けする。"""
        self._interaction_command_scope_factory = factory

    def _cooldown_ticks_of(self, idef: InteractionDef) -> int:
        value = getattr(idef, "cooldown_ticks", 0)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    def _remaining_cooldown_ticks(
        self,
        actor_player_id: PlayerId,
        action_name: str,
        idef: InteractionDef,
        current_tick: Optional[Any],
    ) -> int:
        """あと何 tick 待つ必要があるか。待たなくてよければ 0。

        現在 tick が渡らない経路では間隔を課さない。**課すと、tick を渡さ
        ない既存の呼び出しが「永遠に待たされる」か「常に使える」かの
        どちらかに倒れる。** 後者を選ぶ。tick を知らないのに待たせる判断は
        できない。
        """
        if self._cooldown_store is None or current_tick is None:
            return 0
        cooldown = self._cooldown_ticks_of(idef)
        if cooldown <= 0:
            return 0
        return self._cooldown_store.remaining_ticks(
            actor_player_id,
            idef.cooldown_key,
            cooldown_ticks=cooldown,
            current_tick=int(getattr(current_tick, "value", current_tick)),
            scope=idef.cooldown_scope,
        )

    def _record_cooldown_start(
        self,
        actor_player_id: PlayerId,
        action_name: str,
        idef: InteractionDef,
        current_tick: Optional[Any],
    ) -> None:
        """成功した行為の tick を控える。"""
        if self._cooldown_store is None or current_tick is None:
            return
        if self._cooldown_ticks_of(idef) <= 0:
            return
        self._cooldown_store.record_success(
            actor_player_id,
            idef.cooldown_key,
            int(getattr(current_tick, "value", current_tick)),
            scope=idef.cooldown_scope,
        )

    def _interaction_allows_actor(
        self,
        actor_player_id: Optional[PlayerId],
        idef: InteractionDef,
    ) -> bool:
        """存在層を候補表示と実行拒否の両方で共有する。"""
        plane = actor_plane_for(actor_player_id, self._player_perception_policy)
        if plane is None:
            return False
        return idef.allows_actor_plane(plane)

    def available_action_names(
        self,
        actor_state: Optional[Mapping[str, Any]] = None,
        *,
        actor_player_id: Optional[PlayerId] = None,
    ) -> Tuple[str, ...]:
        """**その行為者に見えている**対人 action 名を宣言順で返す。

        こちらは**識別子**。executor が「人に対して使える操作: ...」を
        列挙する経路で使う。表示用のヒント付き文字列は
        表示用には ``available_action_entries_for`` を使うこと。

        以前は宣言の全件をそのまま返しており、**クルーが操作名を 1 回
        打ち間違えるだけで ``strike_down`` の存在を知れた**。

            人を対象にした 'talk' という操作はありません。
            人に対して使える操作: strike_down, loot_from_downed

        同席者の行では ``available_action_entries_for`` が役割で正しく落として
        いるので、**行で消して隣の案内で教えていた**形だった (claude の指摘)。
        物体側で同じ形を直した PR で、対人側だけ残っていた。

        「識別子が要るから絞れない」は理由にならない。**絞った識別子**を
        返せばよい。判断は ``hidden_interaction_filter`` に 1 つだけ置く。

        ``actor_state`` を渡さない経路は空を返す。全件を返すと、渡し忘れが
        「たまたま全部見える」として静かに漏れる。
        """
        if actor_state is None:
            return ()
        return tuple(
            action_name
            for action_name in visible_action_names_for_state(
                tuple(self._by_action_name.values()), actor_state
            )
            if self._interaction_allows_actor(
                actor_player_id, self._by_action_name[action_name]
            )
        )

    def available_action_labels_for(
        self,
        *,
        target_is_incapacitated: bool,
        target_is_eliminated: bool = False,
        actor_state: Optional[Mapping[str, Any]] = None,
        actor_player_id: Optional[PlayerId] = None,
        target_is_known_ally: bool = False,
    ) -> Tuple[str, ...]:
        """**その相手にいま使える** action の表示ラベルを返す。

        絞り込みに使ってよいのは、その行に既に見えている事実だけである。
        見えていない事実で絞ると、**ラベルの有無そのものが情報漏れになる**。

        **この不変条件は引数の形で強制してある。** 本メソッドとその先の
        ``_is_offerable`` は「その行に見えている公開事実」しか受け取らない。
        対象の役割や隠れた状態はここまで届かないので、それで絞る分岐を
        書こうとしても判定材料が無い。テストで守るより一段強い形になっている
        (この点は claude のレビューで指摘されるまで、私自身も強度を認識して
        いなかった)。

        **引数を増やすときは、それが公開事実かを必ず確認すること。** 秘匿の
        状態をここへ渡した時点で、この保証は静かに消える。

        | 対象の状態 | 公開性 | 扱い |
        |---|---|---|
        | 行動不能 (is_down / is_dead) | 行に出ている | 絞り込みに使う |
        | 既知の相方 | 行に出ている | role と矛盾する行為だけ隠す |
        | 役割 (TARGET_PLAYER_STATE_IS) | 秘匿 | 使わない |
        | 対象の所持 (TARGET_HAS_ITEM) | 行動不能なら行に出ている | いまは使わない |

        ## 行動者自身の状態は別の軸

        ``actor_state`` は**見ている本人**の自由 state で、上の表とは別の話。
        自分の役割は自分が知っている事実なので、これで絞っても新たな情報は
        漏れない。**対象の秘密を守る不変条件と混同しないこと。**

        これが無かったために、クルーの同席者行に「背後から襲う」が全員ぶん
        毎ターン並んでいた。実行すれば「あなたにそんな真似はできない。」で
        必ず失敗する手で、しかもクルーに「自分は人を殺せる」と誤解させる。

        オブジェクトへの行動は候補を組む段階で ``PLAYER_STATE_IS`` を見て
        いるのに、対人行為だけ見ていなかった。**対象の秘密を守る設計が、
        行動者自身の情報まで締め出していた**形になる。

        対象の所持を使わないのは、``item_spec_id_parameter_key`` 形式だと
        判定する品目が実行時にしか決まらないため。「何も持っていない相手に
        take が出る」は残るが、〔手ぶら〕が同じ行に出ているので読み取れる。
        """
        return tuple(
            self._format_entry_as_legacy_label(
                self._action_display_entry(action_name, idef, actor_player_id)
            )
            for action_name, idef in self._by_action_name.items()
            if self._interaction_allows_actor(actor_player_id, idef)
            and self._is_offerable(
                idef,
                target_is_incapacitated=target_is_incapacitated,
                target_is_eliminated=target_is_eliminated,
                actor_state=actor_state,
                target_is_known_ally=target_is_known_ally,
            )
        )

    def available_action_entries_for(
        self,
        *,
        target_is_incapacitated: bool,
        target_is_eliminated: bool = False,
        actor_state: Optional[Mapping[str, Any]] = None,
        actor_player_id: Optional[PlayerId] = None,
        target_is_known_ally: bool = False,
    ) -> Tuple[SpotGraphInteractionEntry, ...]:
        """同席者行へ渡す対人操作を、物体・持ち物と同じ構造で返す。

        対象についての秘匿条件は、候補の有無にも表示ヒントにも使わない。
        対象の役割などが「いまできない」の理由へ漏れるのを防ぎつつ、本人に
        見えている明るさと再使用間隔だけを選べる行から分離する。

        ``target_is_known_ally`` は対象の秘密ではなく、同席者行に既に表示した
        「あなたと同じ側」という関係である。真のときだけ、行動者自身の role
        と矛盾する ``TARGET_PLAYER_STATE_IS`` を隠し、相方への襲撃のような
        必ず失敗する手を提示しない。対象の role 値そのものは受け取らない。
        """
        return tuple(
            self._action_display_entry(action_name, idef, actor_player_id)
            for action_name, idef in self._by_action_name.items()
            if self._interaction_allows_actor(actor_player_id, idef)
            and self._is_offerable(
                idef,
                target_is_incapacitated=target_is_incapacitated,
                target_is_eliminated=target_is_eliminated,
                actor_state=actor_state,
                target_is_known_ally=target_is_known_ally,
            )
        )

    @staticmethod
    def _is_offerable(
        idef: InteractionDef,
        *,
        target_is_incapacitated: bool,
        target_is_eliminated: bool = False,
        actor_state: Optional[Mapping[str, Any]] = None,
        target_is_known_ally: bool = False,
    ) -> bool:
        """公開の対象状態と、行動者自身の状態を見て、その行に出すかを決める。

        ``target_is_eliminated`` も**公開事実**である。行に「死亡している」と
        出ているので、これで絞っても新たな情報は漏れない (この関数の不変条件
        を確認したうえで足している)。

        ## 要求は対称に見る

        以前は「倒れた相手を要求する行動」を立っている相手から隠すだけで、
        **逆が無かった**。実 run で死体の行に「背後から襲う」「持ち物を奪う」
        が並んだのはそのため。

        宣言から要求を導く。``TARGET_PLAYER_IS_INCAPACITATED`` を持つ行動は
        倒れた相手を要求し、持たない行動は立っている相手を要求する。倒れた
        相手を殴れるようにしたいシナリオは、その条件を宣言すれば出せる。

        退場が確定した相手には何も出さない。engine の普遍則
        (`validate_actionable_target`) が実行時に必ず弾くので、出すと
        「選べるのに必ず失敗する手」になる (#860 で潰した形)。

        ## 自分にできない行為は出さない

        ``PLAYER_STATE_IS`` は**行動者自身**の自由 state を見る条件なので、
        候補を組む段階で判定してよい。自分の役割は自分が知っている。

        通常は ``PLAYER_STATE_IS`` だけを見る。``TARGET_PLAYER_STATE_IS`` を
        対象の秘匿 state で評価すると、**誰がクルーかが行動一覧から読めて
        しまう**。例外は ``target_is_known_ally`` が真のときの role 条件だけ。
        この関係は既に同席者行へ出ており、対象の値ではなく行動者自身の role
        から判定できる。条件の種類を増やすときは「その条件が誰の情報を見るか」
        を必ず確認すること。

        ``actor_state`` が渡らない経路 (既存の呼び出し・テスト) では
        絞り込まない。役割条件を持つ行為が出たままになるだけで、いままでと
        同じ挙動に留まる。
        """
        if target_is_eliminated:
            return False
        if actor_state is not None and not _actor_meets_own_state_conditions(
            idef, actor_state
        ):
            return False
        if target_is_known_ally and not _known_ally_meets_target_role_conditions(
            idef, actor_state
        ):
            return False
        return (
            _target_requirement(idef) is TargetRequirement.INCAPACITATED
        ) == target_is_incapacitated

    def _action_display_entry(
        self,
        action_name: str,
        idef: InteractionDef,
        actor_player_id: Optional[PlayerId] = None,
    ) -> SpotGraphInteractionEntry:
        condition_hints = tuple(
            declarative_condition_hints(
                idef,
                item_spec_name_resolver=self._resolve_item_spec_name_for_hint,
            )
        )
        # 「暗い場所のみ」のような宣言だけの条件に加えて、**いまそれを
        # 満たしているか**も書く。行から消さないのが既存の設計で、消すと
        # いつ解禁されるか分からず毎手番試して無駄手になる (#860)。
        #
        # どちらも行為者自身について分かる事実なので、出しても漏れない。
        current_blockers: list[str] = []
        blocked = self._currently_blocking_hint(actor_player_id, idef)
        if blocked:
            current_blockers.append(blocked)
        remaining = self._remaining_cooldown_for_hint(actor_player_id, action_name, idef)
        if remaining > 0:
            current_blockers.append(f"あと{self._span_text(remaining)}")
        return SpotGraphInteractionEntry(
            action_name=action_name,
            display_label=idef.display_label,
            condition_hints=condition_hints,
            # blocked 側の既存 formatter は blocking_hints だけを読む。
            # 宣言条件も併記し、「何の条件が、いまどう不成立か」を一続きで
            # 読めるようにする。対象の秘匿条件は condition_hints に入らない。
            blocking_hints=(
                (*condition_hints, *current_blockers)
                if current_blockers
                else ()
            ),
        )

    @staticmethod
    def _format_entry_as_legacy_label(entry: SpotGraphInteractionEntry) -> str:
        """文字列を返す旧公開口を、構造化表示と同じ内容に保つ。"""
        return format_action_display_with_hints(
            entry.action_name,
            entry.blocking_hints or entry.condition_hints,
            display_label=entry.display_label,
        )

    def _currently_blocking_hint(
        self, actor_player_id: Optional[PlayerId], idef: InteractionDef
    ) -> str:
        """いま明るさの条件を満たしていなければ、その旨を返す。

        実 run 011 で、インポスターが明るい集会室から 3 回続けて襲おうと
        した。行はこう出ていた。

            雰囲気: 明るさ: 明るい / 音: 換気扇の低い唸り / 気温: 暖かい
              ...
              - "モリ" [背後から襲う (strike_down・暗い場所のみ・…)]

        **2 行上に「明るい」と書いてあるのに、選べる手として並んでいた。**
        「暗い場所のみ」という宣言は付いていたが、**いまそれを満たして
        いるかは書いていない**。3 回とも弾かれている。注記だけでは足りない。

        行ごと落とす案も採らない。**明るい部屋に居るインポスターから襲う手が
        消えると、自分の手段そのものを見失う。** 「いまはできない」と書けば、
        暗い所へ移るという次の手に繋がる (``ConditionVisibility.PUBLIC`` の
        既存の分け方と同じ判断)。

        部屋の明るさは**その人の画面に出ている事実**なので、これで絞っても
        新しい情報は漏れない (#860 の不変条件)。
        """
        if actor_player_id is None or self._effective_lighting_resolver is None:
            return ""
        conditions = self._lighting_preconditions(idef)
        if not conditions:
            return ""
        current = self._current_lighting_of(actor_player_id)
        if current is None or self._lighting_conditions_hold(conditions, current):
            return ""
        return f"いまは{lighting_display(current)}"

    @staticmethod
    def _lighting_preconditions(idef: InteractionDef) -> Tuple[Any, ...]:
        """明るさを見る前提条件を宣言順に返す。無ければ空。

        ``_IS`` と ``_IS_NOT`` は**意味が裏返る**ので、要求値をひとつの集合に
        まとめられない。まとめると ``暗い所では不可`` が「暗い所でのみ可」に
        化けて、断りが消える。1 つずつ残して個別に評価する。
        """
        return tuple(
            cond
            for cond in idef.preconditions
            if cond.condition_type in _LIGHTING_CONDITION_TYPES
            and cond.required_lighting is not None
        )

    @staticmethod
    def _lighting_conditions_hold(conditions: Tuple[Any, ...], current: str) -> bool:
        """いまの明るさが、明るさ条件を**すべて**満たすか。

        実行時 (``SpotInteractionService``) と同じ AND で畳む。片方だけ緩いと、
        行の断りと実際の可否が食い違う。
        """
        for cond in conditions:
            matches = current == cond.required_lighting
            is_positive = (
                cond.condition_type is InteractionConditionTypeEnum.SPOT_LIGHTING_IS
            )
            if matches is not is_positive:
                return False
        return True

    def _current_lighting_of(self, actor_player_id: PlayerId) -> Optional[str]:
        """行為者が居る場所のいまの明るさ。spot が graph に無ければ None。

        **例外は握りつぶさない。** resolver 自身が「想定外の例外を None に
        落とさない」と契約していて (``SpotEffectiveLightingResolver.resolve``)、
        ここだけ None に倒すと配線が壊れたときに**断りだけが静かに消える**。
        明るい部屋で「いつでも襲える」と読める行に戻り、しかも誰も気付かない。

        外へ通しても prompt 全体は失わない。呼び出し元の現在状態 builder が
        警告を残して同席者行の対人 action 候補ごと落とす。手段が見つからなく
        なるのは痛いが、嘘の行を出すよりは軽い。

        None を返すのは resolver が None を返したとき、つまり「その spot が
        graph に無い」場合だけ。そのときは推測で書かない。**「いまは明るい」と
        書いて暗い部屋に居る人に嘘を伝える**ほうが害が大きい。
        """
        graph = self._spot_graph_repository.find_graph()
        spot = graph.get_entity_spot(EntityId.create(int(actor_player_id)))
        resolved = self._effective_lighting_resolver.resolve(spot)
        return getattr(resolved, "value", resolved)

    def _remaining_cooldown_for_hint(
        self, actor_player_id: Optional[PlayerId], action_name: str, idef: InteractionDef
    ) -> int:
        """ヒント用の残り tick。分からないときは 0 (何も添えない)。"""
        if actor_player_id is None or self._current_tick_provider is None:
            return 0
        try:
            current = self._current_tick_provider()
        except Exception:
            return 0
        return self._remaining_cooldown_ticks(
            actor_player_id, action_name, idef, current
        )

    def available_action_labels(self) -> Tuple[str, ...]:
        """同席者行に出す**表示用**の action 文字列を宣言順で返す。

        前提条件のうち宣言だけから決まるもの (明るさ / 時刻 / 天候 / 所持品)
        を ``背後から襲う (strike_down・暗い場所のみ・ナイフが要る)`` の形で
        添える。物体行の ``採取する (gather・夜のみ)`` と同じ書式に揃えてある。

        添えないと「暗い場所でだけ襲える」ことは**失敗して初めて**分かる。
        失敗文からも学べるが、行動 1 回とターン 1 つを必ず捨てることになる。
        """
        return tuple(
            format_action_display_with_hints(
                action_name,
                declarative_condition_hints(
                    idef,
                    item_spec_name_resolver=self._resolve_item_spec_name_for_hint,
                ),
                display_label=idef.display_label,
            )
            for action_name, idef in self._by_action_name.items()
        )

    def _resolve_item_spec_name_for_hint(self, spec_id) -> Optional[str]:
        """所持条件のヒント用に品目名を引く。引けなければ None。

        名前が出せないだけで action 候補ごと消すと、宣言した行為が LLM から
        発見できなくなる。ヒントの欠落より候補の消失のほうが重い。
        """
        if self._item_spec_repository is None:
            return None
        try:
            spec = self._item_spec_repository.find_by_id(spec_id)
        except Exception:
            return None
        name = getattr(spec, "name", None) if spec is not None else None
        return str(name) if name else None

    def _span_text(self, ticks: int) -> str:
        """残りの長さを、世界の中にある単位で書く。

        ``あと 13 tick`` と返していた。**tick は世界の中に無い語** (#892)。
        エージェントは毎ターン「現在時刻: 深夜 0:05」を見ているので、
        そこに揃える。実 run 011 でインポスターがこの文を読んでいる。

        分に直せない世界では「手番 N 回ぶん」と書く。裸の数だけを置くと、
        個数にも識別子にも読める (#949 で地図が踏んだ形)。
        """
        return span_text(ticks, self._minutes_per_tick)

    def execute(
        self,
        actor_player_id: PlayerId,
        target_player_id: PlayerId,
        action_name: str,
        *,
        interaction_parameters: Optional[Dict[str, Any]] = None,
        current_tick: Optional[WorldTick] = None,
    ) -> PlayerInteractionResultDto:
        """対人interactionを一つの確定境界で実行する。

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
        scope_factory = self._interaction_command_scope_factory
        declares_call_meeting = any(
            effect.effect_type is InteractionEffectTypeEnum.CALL_MEETING
            for effect in idef.effects
        )
        if scope_factory is None or declares_call_meeting:
            return self._execute_with_repositories(
                actor_player_id,
                target_player_id,
                action_name,
                idef,
                interaction_parameters=interaction_parameters,
                current_tick=current_tick,
                spot_graph_repository=self._spot_graph_repository,
                player_inventory_repository=self._player_inventory_repository,
                item_repository=self._item_repository,
                item_spec_repository=self._item_spec_repository,
                player_status_repository=self._player_status_repository,
                event_publisher=self._event_publisher,
                overflow_sink=self._overflow_sink,
            )

        with scope_factory.create() as context:
            repositories = context.repositories
            event_publisher = _CommandContextEventPublisher(context)
            overflow_sink = self._overflow_sink
            if hasattr(overflow_sink, "bind_to_command"):
                overflow_sink = overflow_sink.bind_to_command(
                    spot_graph_repository=repositories.spot_graph,
                    spot_interior_repository=repositories.spot_interiors,
                    item_repository=repositories.items,
                    item_spec_repository=repositories.item_specs,
                    event_publisher=event_publisher,
                )
            return self._execute_with_repositories(
                actor_player_id,
                target_player_id,
                action_name,
                idef,
                interaction_parameters=interaction_parameters,
                current_tick=current_tick,
                spot_graph_repository=repositories.spot_graph,
                player_inventory_repository=repositories.player_inventories,
                item_repository=repositories.items,
                item_spec_repository=repositories.item_specs,
                player_status_repository=repositories.player_statuses,
                event_publisher=event_publisher,
                overflow_sink=overflow_sink,
            )

    def _execute_with_repositories(
        self,
        actor_player_id: PlayerId,
        target_player_id: PlayerId,
        action_name: str,
        idef: InteractionDef,
        *,
        interaction_parameters: Optional[Dict[str, Any]] = None,
        current_tick: Optional[WorldTick] = None,
        spot_graph_repository: ISpotGraphRepository,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
        item_spec_repository: ItemSpecRepository,
        player_status_repository: Optional[PlayerStatusRepository],
        event_publisher: Optional[Any],
        overflow_sink: Any,
    ) -> PlayerInteractionResultDto:
        """解決済み定義をcommand専用repositoryだけで適用する。"""
        if not self._interaction_allows_actor(actor_player_id, idef):
            plane = actor_plane_for(
                actor_player_id, self._player_perception_policy
            )
            raise InteractionActorPlaneNotAllowedException(
                actor_plane_refusal_message(plane)
            )
        if int(actor_player_id) == int(target_player_id):
            # 自分を対象にした対人行為は、成立しても意味が無いうえに
            # 「対象から奪って自分に渡す」が no-op になって成功として返る。
            raise ApplicationException(
                "自分自身を対象にはできません。",
                player_id=int(actor_player_id),
            )

        graph = spot_graph_repository.find_graph()
        actor_spot = graph.get_entity_spot(EntityId.create(int(actor_player_id)))
        target_was_down = self._player_life_query.has_reportable_body(
            target_player_id
        )
        actor_status = None
        target_status = None
        if player_status_repository is not None:
            actor_status = player_status_repository.find_by_id(actor_player_id)
            target_status = player_status_repository.find_by_id(target_player_id)
        if target_was_down:
            body = self._fallen_body_registry.find(target_player_id)
            if body is None:
                raise ApplicationException(
                    "倒れている相手の身体位置が記録されていません。",
                    player_id=int(actor_player_id),
                )
            target_spot = body.spot_id
        else:
            target_spot = graph.get_entity_spot(
                EntityId.create(int(target_player_id))
            )
        if actor_spot != target_spot:
            raise ApplicationException(
                "相手が同じ場所にいません。",
                player_id=int(actor_player_id),
            )

        rejection = validate_actionable_target(
            actor_player_id=int(actor_player_id),
            target_player_id=int(target_player_id),
            # 行為者自身の可否は allowed_actor_planes とシナリオ前提条件が
            # 既に決めている。ここで身体状態まで重ねると、DEPARTED に許可した
            # 対人操作を一律に塞ぐため、再検証するのは競合した対象だけに絞る。
            actor_status=None,
            target_status=target_status,
            target_outcome=self._player_life_query.outcome_of(target_player_id),
            same_spot=True,
            requirement=_target_requirement(idef),
            target_display_name="その相手",
        )
        if rejection is not None:
            message = (
                "その相手はもう倒れている。"
                if rejection.code in {"TARGET_IS_DOWN", "TARGET_IS_ELIMINATED"}
                and _target_requirement(idef) is TargetRequirement.ACTIVE
                else rejection.message
            )
            raise InteractionNotAllowedException(message)

        actor_inv = self._require_inventory(
            actor_player_id, player_inventory_repository
        )
        target_inv = self._require_inventory(
            target_player_id, player_inventory_repository
        )

        # 効果を当てる前に対象の状態を控える。適用後に問い合わせると、
        # 昏倒させた一撃そのものが「倒れている間にされたこと」に化ける。
        owned = collect_owned_item_spec_ids_from_inventory(
            actor_inv, item_repository
        )
        owned_counts = count_owned_item_instances_by_spec(
            actor_inv, item_repository
        )
        target_owned = collect_owned_item_spec_ids_from_inventory(
            target_inv, item_repository
        )
        spot_presence_count = len(graph.presence_at(actor_spot).present_entity_ids)

        # LLM は「太い流木を奪う」のように**名前**で品目を指す (倒れた相手の
        # 持ち物は prompt に出ている: PR #824)。domain 側は spec id しか扱わ
        # ないので、名前 → spec id の解決はここで済ませて
        # ``interaction_parameters`` に入れておく。見つからないときは入れない
        # ままにして、``TARGET_HAS_ITEM`` に「相手はそれを持っていない」と
        # 言わせる (ここで例外にすると LLM が学習できない失敗になる)。
        resolved_parameters = self._with_resolved_item_spec_id(
            interaction_parameters,
            target_inv,
            item_repository,
            item_spec_repository,
        )

        # 再使用間隔。**前提条件より先に見る。**
        #
        # あとに置くと「暗くないので襲えない」が先に返り、待たされている
        # ことが分からない。行為者自身の状態なので、伝えても何も漏れない。
        remaining = self._remaining_cooldown_ticks(
            actor_player_id, action_name, idef, current_tick
        )
        if remaining > 0:
            raise InteractionNotAllowedException(
                f"まだ間を置く必要がある。あと{self._span_text(remaining)}。"
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

        removal_requirements = self._effect_service.plan_item_removals(
            interior=SpotInterior((), (), (), ()),
            acting_object=None,
            effects=idef.effects,
            interaction_parameters=resolved_parameters,
            owned_item_spec_counts=owned_counts,
            target_player_status=target_status,
        )
        self._require_removable_items(
            target_inv,
            removal_requirements.target_item_spec_ids,
            target_player_id,
            "対象",
            item_repository,
        )
        self._require_removable_items(
            actor_inv,
            removal_requirements.actor_item_spec_ids,
            actor_player_id,
            "行為者",
            item_repository,
        )

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

        # 受け取る側に空きがあるか、**何も動かす前に**確かめる。
        #
        # PlayerInventoryAggregate.acquire_item は満杯のとき黙って捨てる
        # (overflow event を積むだけで例外にしない)。先に取り上げてから渡すと
        # 「対象からは消えて行為者には入らない」= アイテムが世界から消滅し、
        # しかも成功として返るので誰も気づけない。
        self._require_free_slots(
            actor_player_id,
            len(result.item_spec_ids_to_grant),
            "あなた",
            player_inventory_repository,
        )
        self._require_free_slots(
            target_player_id,
            len(result.target_item_spec_ids_to_grant),
            "相手",
            player_inventory_repository,
        )
        self._world_flag_state.replace_from_interaction(
            result.new_flags,
            context=WorldFlagMutationContext(
                source=WorldFlagMutationSource.PLAYER_INTERACTION,
                actor_player_id=int(actor_player_id),
            ),
        )

        # 先に対象から取り上げ、次に行為者へ渡す。順序を逆にすると、対象が
        # 持っていなかった場合に「行為者は受け取ったが対象は失っていない」
        # という複製が一瞬成立してしまう。
        self._remove_from(
            target_player_id,
            result.target_item_spec_ids_to_remove,
            "対象",
            player_inventory_repository,
            item_repository,
        )
        self._remove_from(
            actor_player_id,
            result.item_spec_ids_to_remove,
            "行為者",
            player_inventory_repository,
            item_repository,
        )
        self._grant_to(
            target_player_id,
            result.target_item_spec_ids_to_grant,
            player_inventory_repository,
            item_repository,
            item_spec_repository,
            overflow_sink,
        )
        self._grant_to(
            actor_player_id,
            result.item_spec_ids_to_grant,
            player_inventory_repository,
            item_repository,
            item_spec_repository,
            overflow_sink,
        )

        if result.acting_player_state_changed and actor_status is not None:
            player_status_repository.save(actor_status)  # type: ignore[union-attr]

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
            if event_publisher is not None:
                status_events_from_damage.extend(actor_status.get_events())
                actor_status.clear_events()
            player_status_repository.save(actor_status)  # type: ignore[union-attr]
        if result.target_damage_specs and target_status is not None:
            for spec in result.target_damage_specs:
                if spec.damage <= 0:
                    continue
                target_status.apply_damage(
                    spec.damage, killer_player_id=actor_player_id
                )
            if event_publisher is not None:
                status_events_from_damage.extend(target_status.get_events())
                target_status.clear_events()
            player_status_repository.save(target_status)  # type: ignore[union-attr]

        declared_witness_message = (
            declared_observation_message_for_lighting(
                actor_spot,
                resolver=self._effective_lighting_resolver,
                bright=idef.witness_observation_message,
                dark=idef.witness_observation_message_in_dark,
            )
            or ""
        )
        if (
            declared_witness_message.strip()
            and idef.witness_policy is WitnessPolicy.SAME_SPOT
        ):
            status_events_from_damage = [
                replace(
                    event,
                    declared_witness_prose_replaces_bystander_prose=True,
                )
                if isinstance(event, PlayerDownedEvent)
                else event
                for event in status_events_from_damage
            ]

        # 観測を伴わない対人行為は作らない。state だけ変わって誰にも何も
        # 見えないと、被害者は次のターンに持ち物が消えていることに気づく
        # だけになり、trace からも効果を確認できない。
        #
        # publisher 未注入は配線漏れだが、ここで落とすと実験そのものが
        # 止まる。警告を残して行為自体は成立させる (観測が消えたことは
        # 警告で追える)。
        if event_publisher is None:
            _logger.warning(
                "PlayerInteractionApplicationService に event_publisher が "
                "注入されていないため、対人行為 %r の観測が誰にも届きません",
                action_name,
            )
        else:
            event_publisher.publish_all([
                *status_events_from_damage,
                PlayerInteractedWithPlayerEvent.create(
                    aggregate_id=graph.graph_id,
                    aggregate_type="SpotGraphAggregate",
                    entity_id=EntityId.create(int(actor_player_id)),
                    target_entity_id=EntityId.create(int(target_player_id)),
                    spot_id=actor_spot,
                    action_name=action_name,
                    result_message="; ".join(result.messages),
                    action_display_label=idef.effective_display_label,
                    witness_observation_message=declared_witness_message,
                    witness_policy=idef.witness_policy,
                    target_was_down=target_was_down,
                    notify_target=idef.notify_target,
                    target_observation_message=(
                        idef.target_observation_message or ""
                    ),
                )
            ])

        # 成功が確定してから起点を更新する。**空振りでは更新しない。**
        # 前提条件を確かめる行動そのものが罰になると、条件を試せなくなる。
        self._record_cooldown_start(actor_player_id, action_name, idef, current_tick)

        return PlayerInteractionResultDto(
            action_name=action_name,
            actor_player_id=int(actor_player_id),
            target_player_id=int(target_player_id),
            messages=tuple(result.messages),
            action_display_label=idef.effective_display_label,
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
        item_repository: ItemRepository,
        item_spec_repository: ItemSpecRepository,
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
        spec_id = self._find_spec_id_by_name(
            target_inventory,
            raw_name.strip(),
            item_repository,
            item_spec_repository,
        )
        if spec_id is None:
            return interaction_parameters
        return {**interaction_parameters, self.ITEM_SPEC_ID_KEY: spec_id.value}

    def _find_spec_id_by_name(
        self,
        inventory,
        name: str,
        item_repository: ItemRepository,
        item_spec_repository: ItemSpecRepository,
    ):
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
                inventory, item_repository
            )
            if self._spec_name(spec_id, item_spec_repository) == name
        ]
        if len(matches) > 1:
            raise InteractionNotAllowedException(
                f"「{name}」に当てはまるものが相手の持ち物に複数ある。"
                "どれを指すのか決められないので、別の物を指定すること。"
            )
        return matches[0] if matches else None

    def _spec_name(
        self, spec_id, item_spec_repository: ItemSpecRepository
    ) -> Optional[str]:
        spec = item_spec_repository.find_by_id(spec_id)
        return getattr(spec, "name", None) if spec is not None else None

    def _require_free_slots(
        self,
        player_id: PlayerId,
        needed: int,
        who: str,
        player_inventory_repository: PlayerInventoryRepository,
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

        inv = self._require_inventory(player_id, player_inventory_repository)
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

    def _require_inventory(
        self,
        player_id: PlayerId,
        player_inventory_repository: PlayerInventoryRepository,
    ):
        inv = player_inventory_repository.find_by_id(player_id)
        if inv is None:
            raise ApplicationException(
                f"インベントリが見つかりません: {player_id}",
                player_id=int(player_id),
            )
        return inv

    def _grant_to(
        self,
        player_id: PlayerId,
        spec_ids,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
        item_spec_repository: ItemSpecRepository,
        overflow_sink: Any,
    ) -> None:
        if not spec_ids:
            return
        grant_item_specs_to_inventory(
            player_id,
            tuple(spec_ids),
            item_repository,
            item_spec_repository,
            player_inventory_repository,
            overflow_sink=overflow_sink,
        )

    def _remove_from(
        self,
        player_id: PlayerId,
        spec_ids,
        who: str,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
    ) -> None:
        """指定プレイヤーの所持品から spec_ids を 1 個ずつ取り除く。

        取り除けないときは黙って飛ばさず例外にする。前提条件で所持を確認した
        うえで来ているので、ここで足りないのは何かが壊れている状態であり、
        飛ばすと「奪えたはずが何も起きていないのに成功と返る」ことになる。
        """
        if not spec_ids:
            return
        inv = self._require_inventory(player_id, player_inventory_repository)
        if not remove_items_of_specs_from_inventory(
            inv, tuple(spec_ids), item_repository
        ):
            raise ApplicationException(
                f"{who}の所持品から必要数を取り除けませんでした; "
                "前提条件との不一致",
                player_id=int(player_id),
            )
        player_inventory_repository.save(inv)

    def _require_removable_items(
        self,
        inventory,
        spec_ids,
        player_id: PlayerId,
        who: str,
        item_repository: ItemRepository,
    ) -> None:
        """両者の所持品を動かす前に、未予約品から削除全量を確保できるか検証する。"""
        if plan_item_removals_from_inventory(
            inventory, tuple(spec_ids), item_repository
        ) is None:
            raise InteractionNotAllowedException(
                f"{who}の品は別の取引や依頼に確保されているか、必要数に足りない。"
            )
