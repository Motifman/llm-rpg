"""PlayerCurrentStateDto 用のスポットグラフスナップショット構築"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Callable, FrozenSet, Iterator, Mapping, Optional, Sequence

from ai_rpg_world.application.world_graph.distant_view_service import (
    DistantViewArea,
    DistantViewCandidate,
    DistantViewConnection,
    DistantViewResult,
    DistantViewService,
    DistantViewSpot,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphAgentStatusEntry,
    SpotGraphAtmosphereEntry,
    SpotGraphConnectionEntry,
    SpotGraphGroundItemEntry,
    SpotGraphInteractionEntry,
    SpotGraphInventoryItemEntry,
    SpotGraphMarketOwnOrderEntry,
    SpotGraphMerchantEntry,
    SpotGraphMerchantPriceEntry,
    SpotGraphMonsterEntry,
    SpotGraphNearbyEntityEntry,
    SpotGraphObjectEntry,
    SpotGraphPlayerSnapshotDto,
    SpotGraphSubLocationEntry,
    SpotGraphTimeOfDayEntry,
    SpotGraphWeatherEntry,
)
from ai_rpg_world.domain.world_graph.value_object.time_of_day import TimeOfDay
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_attribute_spec import (
    PlayerAttributeSpecs,
)
from ai_rpg_world.application.world_graph.unreachable_attribute_notes import (
    unreachable_attribute_notes,
)
from ai_rpg_world.application.player.services.fallen_body_registry import (
    FallenBodyRegistry,
)
from ai_rpg_world.application.player.services.player_perception_policy import (
    PlayerPerceptionPolicy,
)
from ai_rpg_world.application.player.services.departed_position_store import (
    DepartedPositionStore,
)
from ai_rpg_world.domain.world_graph.enum.interaction_actor_plane import (
    InteractionActorPlane,
)
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import EntityNotInGraphException
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import ISpotGraphRepository
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import ISpotInteriorRepository
from ai_rpg_world.domain.world_graph.service.stock_pool_regen import compute_stock_regen
from ai_rpg_world.domain.world_graph.service.item_interaction_registry import (
    ItemInteractionRegistry,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
    TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
)
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.application.world_graph.hidden_interaction_filter import (
    visible_interactions,
    visible_interactions_for_actor_plane,
)
from ai_rpg_world.application.world_graph.interaction_condition_hint_text import (
    declarative_condition_hints,
    format_action_display_with_hints,
    required_parameter_hints,
)
from ai_rpg_world.domain.world_graph.service.spot_perception_service import SpotPerceptionService
from ai_rpg_world.application.world_graph.spot_effective_lighting_resolver import (
    SpotEffectiveLightingResolver,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.state_display_rule import (
    state_display_values_equal,
)

from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.memory.goal.service.stagnation_pressure_band import (
    STAGNATION_PRESSURE_BAND_NONE,
)

logger = logging.getLogger(__name__)


def _has_failing_object_state_precondition(interaction, interior) -> bool:
    """interaction の OBJECT_STATE precondition が現在 失敗しているか判定する。

    第24回実験 (#343) で cockpit を 19 回 retry した silent failure の対策。
    OBJECT_STATE は「取り尽くした」「もう空だ」のような永続失敗を持つ唯一の
    precondition 種別。HAS_ITEM / TIME_OF_DAY / WEATHER 等のプレイヤー / 環境
    依存は対象外。

    現在は action を隠すためではなく、失敗理由ヒントを prompt に添えるための
    判定に使う。action 自体を落とすと、LLM が存在しない操作名を発明する原因に
    なるため。
    """
    return bool(_object_state_precondition_failure_hints(interaction, interior))


def _object_state_precondition_failure_hints(interaction, interior) -> tuple[str, ...]:
    """現在失敗している OBJECT_STATE precondition の failure_message を返す。"""
    hints: list[str] = []
    for cond in interaction.preconditions:
        if cond.condition_type != InteractionConditionTypeEnum.OBJECT_STATE:
            continue
        if cond.target_object_id is None or not cond.required_state:
            continue
        target = interior.get_object(cond.target_object_id)
        if target is None:
            continue
        for key, required_value in cond.required_state.items():
            if target.state.get(key) != required_value:
                message = str(cond.failure_message).strip()
                hints.append(message or "現在は条件を満たしていない")
                break
    return tuple(hints)


def _object_stock_precondition_failure_hints(
    interaction,
    interior,
    *,
    current_tick: Optional[int],
) -> tuple[str, ...]:
    """現在失敗している OBJECT_STOCK_AT_LEAST の failure_message を返す。

    備蓄の現在値は domain 側と同じ ``compute_stock_regen`` で遅延算出する。
    """
    hints: list[str] = []
    for cond in interaction.preconditions:
        if cond.condition_type != InteractionConditionTypeEnum.OBJECT_STOCK_AT_LEAST:
            continue
        if cond.target_object_id is None:
            continue
        target = interior.get_object(cond.target_object_id)
        if target is None:
            continue
        state = target.state
        try:
            required = max(1, int(cond.required_quantity))
            now = (
                int(current_tick)
                if current_tick is not None
                else int(state.get("stock_tick", 0))
            )
            result = compute_stock_regen(
                stock=int(state.get("stock", 0)),
                capacity=int(state.get("stock_capacity", 0)),
                stock_tick=int(state.get("stock_tick", 0)),
                refill_interval=int(state.get("stock_refill_interval", 0)),
                now=now,
            )
        except (TypeError, ValueError):
            logger.warning(
                "invalid object stock state for interaction hint: action_name=%s object_id=%s",
                getattr(interaction, "action_name", None),
                getattr(cond.target_object_id, "value", cond.target_object_id),
                exc_info=True,
            )
            continue
        if result.effective_stock < required:
            message = str(cond.failure_message).strip()
            hints.append(message or "備蓄が足りません。時間が経てば回復する")
    return tuple(hints)


def _object_state_int_precondition_failure_hints(
    interaction,
    interior,
) -> tuple[str, ...]:
    """未達の OBJECT_STATE_INT_AT_LEAST を、必要数と現在数つきで返す。"""
    hints: list[str] = []
    for cond in interaction.preconditions:
        if cond.condition_type != InteractionConditionTypeEnum.OBJECT_STATE_INT_AT_LEAST:
            continue
        if cond.target_object_id is None or not cond.state_key:
            continue
        target = interior.get_object(cond.target_object_id)
        if target is None:
            continue
        required = max(1, int(cond.required_quantity))
        current = target.state.get(cond.state_key, 0)
        if not isinstance(current, int):
            current = 0
        if current < required:
            message = str(cond.failure_message).strip()
            hints.append(
                message
                or f"必要な量が足りません (必要: {required}, いま: {current})"
            )
    return tuple(hints)


# PR #2 状態異常 surface: StatusEffectType.value → 日本語ラベル。
# enum.value (英語) のままだと LLM が「これは何の状態異常?」と混乱するので
# プロンプト表示用に日本語化する。未知の effect_type は value をそのまま出す。
_STATUS_EFFECT_LABELS: dict[str, str] = {
    "bleeding": "出血",
    "poison": "毒",
    "hypothermia": "低体温",
    "infected": "感染症",
    "regeneration": "回復",
    "exhausted": "疲労困憊",
    "stun": "気絶",
    "silence": "沈黙",
    "blind": "暗闇",
    "burn": "火傷",
    "freeze": "凍結",
    "sleep": "睡眠",
    "paralysis": "麻痺",
}

def _interaction_condition_hints(
    interaction,
    interior=None,
    phase_label_resolver=None,
) -> tuple[str, ...]:
    """物体 action 表示用の宣言由来ヒントを組む。

    宣言だけから決まるぶん (時刻 / 天候 / 明るさ) は
    ``declarative_condition_hints`` に委譲する。同席者行の対人 action も
    同じ関数を使うので、書式と語彙が経路ごとにずれない。
    """
    def resolve_state_requirement(cond) -> Optional[str]:
        if interior is None or cond.target_object_id is None or not cond.state_key:
            return None
        target = interior.get_object(cond.target_object_id)
        if target is None:
            return None
        required = max(1, int(cond.required_quantity))
        rule = next(
            (
                rule
                for rule in target.state_display
                if rule.key == cond.state_key
                and state_display_values_equal(rule.value, required)
            ),
            None,
        )
        return f"{rule.text}こと" if rule is not None else None

    return tuple((
        *declarative_condition_hints(
            interaction,
            object_state_requirement_text_resolver=resolve_state_requirement,
            time_of_day_phase_label_resolver=phase_label_resolver,
        ),
        *required_parameter_hints(interaction),
    ))


def _interaction_blocking_hints(
    interaction,
    interior=None,
    *,
    current_tick: Optional[int] = None,
) -> tuple[str, ...]:
    """物体 action 表示用の「いま満たしていない理由」を組む。

    HAS_ITEM は他の表示や remediation と重複するため物体行では出さない
    (= resolver を渡さない)。OBJECT_STATE / OBJECT_STATE_INT_AT_LEAST /
    OBJECT_STOCK_AT_LEAST は現在
    失敗している場合だけ failure_message を添え、action 候補自体は残す。
    候補集合を消すと存在しない操作名の発明につながるため。

    ``AT_SPOT_IS`` も扱わない。物体の action 候補は「その物体が在るスポット」
    でしか表示されないので、場所を添えても常に自明な情報になる。
    """
    if interior is None:
        return ()
    hints: list[str] = list(
        _object_state_precondition_failure_hints(interaction, interior)
    )
    hints.extend(_object_state_int_precondition_failure_hints(interaction, interior))
    hints.extend(
        _object_stock_precondition_failure_hints(
            interaction,
            interior,
            current_tick=current_tick,
        )
    )
    return tuple(hints)


def _format_interaction_action_name_with_hints(
    interaction,
    interior=None,
    *,
    current_tick: Optional[int] = None,
    phase_label_resolver=None,
) -> str:
    """fallback テキスト用に action_name と表示ヒントを同じ規則で整形する。"""
    blocking_hints = _interaction_blocking_hints(
        interaction,
        interior,
        current_tick=current_tick,
    )
    if blocking_hints:
        return "いまできない: " + format_action_display_with_hints(
            interaction.action_name,
            blocking_hints,
            display_label=interaction.display_label,
        )
    hints = _interaction_condition_hints(
        interaction,
        interior,
        phase_label_resolver,
    )
    return format_action_display_with_hints(
        interaction.action_name,
        hints,
        display_label=interaction.display_label,
    )

EntityNameResolver = Callable[[int], str]
WeatherProvider = Callable[[], Optional[WeatherState]]
WorldFlagsProvider = Callable[[], frozenset[str]]
OwnedItemSpecIdsProvider = Callable[[int], FrozenSet[ItemSpecId]]
# item_spec_id (int) → 表示名 (str) のラッパ。ground_items 表示で使う。
# 未解決時は空文字列 or "アイテム#N" のような fallback を返してよい。
ItemSpecNameResolver = Callable[[int], str]
# 現在 tick の TimeOfDay を返す provider。シナリオが昼夜サイクルを宣言して
# いなければ None を返す (= プロンプトに時刻行が出ない)。
TimeOfDayProvider = Callable[[], Optional[TimeOfDay]]
# モンスター個体 ID から「肉眼で観測できる範囲の view DTO」を返す resolver。
# 名前解決と内部 state の可視化（HP バケット化・behavior の日本語化）を application 層で行う。
# None を返した場合は builder 側で当該個体を snapshot から黙って除外する（既に死んで掃除されたケース等）。
MonsterViewProvider = Callable[[MonsterId], Optional[SpotGraphMonsterEntry]]
VisibleMonsterObserver = Callable[[int, SpotGraphMonsterEntry], None]
#: 同じ場所で倒れている / 死んでいる人を見た、という通知。
#: 引数は (見た人の player_id, 倒れている人の entity_id, 表示名, 退場が確定したか)。
FallenBodyObserver = Callable[[int, int, str, bool], None]
# P-U3/P-U4 (停滞感の表出): player_id (int) → 停滞感バンド (``none`` /
# ``light`` / ``strong``、P-U2 の resolve_stagnation_pressure_band と同型)。
# 自己 (own_stagnation_band) と他者 (nearby_entities の stagnation_band) の
# 両方がこの provider を共有する。未注入なら常に none 相当に縮退する。
StagnationBandProvider = Callable[[int], str]
#: 見る側が、対象を自分と同じ側だと既に知っているかを返す。
#: 役割名そのものを prompt の状態組み立てへ持ち込まないため、真偽だけを渡す。
KnownAllyChecker = Callable[[PlayerId, PlayerId], bool]


class SpotGraphCurrentStateBuilder:
    """グラフ・内部データ・プレイヤー状態からスナップショットを組み立てる。

    知覚フィルタを有効にするには、以下のパラメータをワイヤリング時に渡す:
    - ``light_source_item_spec_ids``: 光源として扱うアイテムのID集合
    - ``owned_item_spec_ids_provider``: エンティティIDからアイテム所持を返すコールバック
    これらが未設定の場合、照明フィルタは無効（全オブジェクト表示）となる。
    """

    def __init__(
        self,
        spot_graph_repository: ISpotGraphRepository,
        spot_interior_repository: ISpotInteriorRepository,
        player_status_repository: PlayerStatusRepository,
        fallen_body_registry: FallenBodyRegistry,
        *,
        player_perception_policy: Optional[PlayerPerceptionPolicy] = None,
        departed_position_store: Optional[DepartedPositionStore] = None,
        entity_name_resolver: Optional[EntityNameResolver] = None,
        inventory_builder: Optional[Callable[[PlayerId], tuple]] = None,
        weather_provider: Optional[WeatherProvider] = None,
        world_flags_provider: Optional[WorldFlagsProvider] = None,
        light_source_item_spec_ids: FrozenSet[ItemSpecId] = frozenset(),
        owned_item_spec_ids_provider: Optional[OwnedItemSpecIdsProvider] = None,
        monster_view_provider: Optional[MonsterViewProvider] = None,
        item_spec_name_resolver: Optional[ItemSpecNameResolver] = None,
        time_of_day_provider: Optional[TimeOfDayProvider] = None,
        time_of_day_phase_label_resolver: Optional[Callable[[str], Optional[str]]] = None,
        item_state_resolver: Optional[Callable[[int], Optional[dict]]] = None,
        current_tick_provider: Optional[Callable[[], int]] = None,
        minutes_per_tick: Optional[int] = None,
        stagnation_band_provider: Optional[StagnationBandProvider] = None,
        dead_player_checker: Optional[Callable[[PlayerId], bool]] = None,
        areas: Sequence[Any] = (),
        distant_cues: Sequence[Any] = (),
        distant_view_service: Optional[DistantViewService] = None,
        distant_view_trace_enabled: bool = False,
        trace_recorder_provider: Optional[Callable[[], Any]] = None,
        visible_monster_observer: Optional[VisibleMonsterObserver] = None,
        # 倒れている人を見たことを runtime へ通知する hook。初回判定と観測の
        # 生成は runtime 側の責務で、builder は「目に入った」事実だけを渡す。
        fallen_body_observer: Optional[FallenBodyObserver] = None,
        # 人を対象にできる action の構造化表示を返す provider (シナリオ直下
        # ``player_interactions``)。未注入なら空 = 同席者行に action を出さない
        # (対人行為を宣言していない世界での挙動と一致)。
        player_action_entries_provider: Optional[
            Callable[..., Sequence[SpotGraphInteractionEntry]]
        ] = None,
        known_ally_checker: Optional[KnownAllyChecker] = None,
        # この世界にそのツールが存在するかを訊く口。組み込みツールを行に
        # 宣伝する前に必ず通す。未注入なら従来どおり全部出す。
        is_tool_exposed: Optional[Callable[[str], bool]] = None,
        # 自由 state の呼び名。engine のキーをプロンプトへ出さないため。
        state_display_names: Optional[Mapping[str, Any]] = None,
        # 人が持つ属性の宣言。未注入なら注記は増えず、既存の世界の prompt は
        # 1 ビットも変わらない。
        player_attribute_specs: Optional[PlayerAttributeSpecs] = None,
        hidden_player_state_keys: Optional[Any] = None,
        item_interaction_registry: Optional[ItemInteractionRegistry] = None,
        # 経済統合 Phase 1: シナリオが宣言した NPC 商人
        # (``ScenarioLoadResult.merchants``)。空なら商人節も所持金行も出さない
        # = 宣言していない世界の prompt は 1 文字も変わらない。
        merchants: Sequence[Any] = (),
        market_service: Optional[Any] = None,
        # 経済統合 Phase 2: 自分宛ての申し出を出すための口。未注入なら常に空
        # (取引を宣言しない世界と同じ挙動)。
        incoming_trade_offers_provider: Optional[Callable[[int], Sequence[Any]]] = None,
    ) -> None:
        self._spot_graph_repository = spot_graph_repository
        self._spot_interior_repository = spot_interior_repository
        self._player_status_repository = player_status_repository
        self._fallen_body_registry = fallen_body_registry
        self._player_perception_policy = player_perception_policy
        self._departed_position_store = departed_position_store
        self._entity_name_resolver = entity_name_resolver
        self._inventory_builder = inventory_builder
        self._weather_provider = weather_provider
        self._world_flags_provider = world_flags_provider
        self._light_source_item_spec_ids = light_source_item_spec_ids
        self._owned_item_spec_ids_provider = owned_item_spec_ids_provider
        self._monster_view_provider = monster_view_provider
        self._item_spec_name_resolver = item_spec_name_resolver
        self._merchants = tuple(merchants)
        self._market_service = market_service
        self._incoming_trade_offers_provider = incoming_trade_offers_provider
        self._time_of_day_provider = time_of_day_provider
        self._time_of_day_phase_label_resolver = time_of_day_phase_label_resolver
        # Phase D-3a: 地面アイテムの spoiled 表示用。instance_id → state dict
        # (None なら spoiled 不明)。None なら spoiled は常に False 扱いになり、
        # この拡張を使わないシナリオ (脱出ゲーム本編など) に無影響。
        self._item_state_resolver = item_state_resolver
        # PR #2 状態異常 surface: 残り tick 表示用 (None なら effect 名のみ表示)
        self._current_tick_provider = current_tick_provider
        self._minutes_per_tick = minutes_per_tick
        # P-U3/P-U4 (停滞感の表出): 未注入 (None) なら自己・他者とも常に
        # STAGNATION_PRESSURE_BAND_NONE (= 何も描画しない、導入前と挙動一致)。
        self._stagnation_band_provider = stagnation_band_provider
        # 同 spot の他 player が DEAD (終局・復活不可) かを返す checker。未注入なら
        # 常に False (= 死亡表示を出さない、導入前と挙動一致)。outcome は
        # PlayerStatusAggregate ではなく PlayerOutcomeRegistry 側にあるので、
        # runtime 配線でそこを引く callable を渡す。
        self._dead_player_checker = dead_player_checker
        self._areas = tuple(areas)
        self._distant_cues = tuple(distant_cues)
        self._distant_view_service = distant_view_service or DistantViewService()
        self._distant_view_trace_enabled = distant_view_trace_enabled
        self._trace_recorder_provider = trace_recorder_provider
        self._visible_monster_observer = visible_monster_observer
        self._fallen_body_observer = fallen_body_observer
        self._player_action_entries_provider = player_action_entries_provider
        self._known_ally_checker = known_ally_checker
        # 物体操作の待ち時間を行に添える provider。未注入なら何も添えない。
        # service をそのまま持たせると builder が実行経路に依存するので、
        # 「残りの断りを 1 つ返す」だけの関数として受け取る。
        self._object_cooldown_hint_provider: Optional[Any] = None
        self._item_cooldown_hint_provider: Optional[Any] = None
        self._item_interaction_registry = (
            item_interaction_registry or ItemInteractionRegistry()
        )
        self._is_tool_exposed = is_tool_exposed
        self._state_display_names = dict(state_display_names or {})
        # 手番を記録する効果が書く本人 state の key。表示から外す (#892)。
        # 物体 state と違い本人 state に hidden_state_keys が無いので、
        # 宣言から導出したものを受け取る。
        self._player_attribute_specs = player_attribute_specs
        self._hidden_player_state_keys: frozenset = frozenset(
            hidden_player_state_keys or ()
        )
        self._perception = SpotPerceptionService()
        # 実効照明は前提条件 (SPOT_LIGHTING_IS) と同じ resolver で求める。
        # 2 か所に同じ合成ロジックを置くと、片方だけ直したときに「prompt は
        # 暗いと言っているのに条件は明るいと判定する」状態になる。
        self._lighting_resolver = SpotEffectiveLightingResolver(
            spot_graph_repository=spot_graph_repository,
            entity_has_light_source=self._entity_has_light_source,
            time_of_day_provider=time_of_day_provider,
            weather_provider=weather_provider,
            perception=self._perception,
        )

    @contextmanager
    def suppress_observation_notifications(self) -> Iterator[None]:
        """起動時の読み取り専用検査中だけ、初回観測の通知を止める。

        snapshot 構築は見えている monster と倒れた人を通常なら通知し、
        Encounter Memory の「一度きり」を消費する。runtime を公開する前の
        起動時検査だけで使い、終了時には例外の有無にかかわらず observer を
        元へ戻す。
        """
        visible_monster_observer = self._visible_monster_observer
        fallen_body_observer = self._fallen_body_observer
        self._visible_monster_observer = None
        self._fallen_body_observer = None
        try:
            yield
        finally:
            self._visible_monster_observer = visible_monster_observer
            self._fallen_body_observer = fallen_body_observer

    def _resolve_player_action_entries(
        self,
        *,
        is_incapacitated: bool,
        is_eliminated: bool = False,
        actor_state: Mapping[str, Any] | None = None,
        actor_player_id_value: int | None = None,
        target_player_id_value: int | None = None,
    ) -> tuple:
        """その相手に提示する対人 action の構造化 entry。未注入なら空。

        **対象**についての絞り込みの入力は、その行に既に見えている事実だけに
        する (`is_down` / `is_dead` / `同じ側`)。見えていない事実で絞ると、
        ラベルの有無そのものが情報漏れになる。相方の役割名は渡さず、同じ行に
        表示済みの関係だけを真偽値へ畳む。

        ``actor_state`` は**見ている本人**の自由 state。自分の役割は自分が
        知っている事実なので、これで絞っても新たな情報は漏れない。対象の
        秘密を守る不変条件とは別の軸で、混同しないこと。

        provider が落ちても現在状態の生成そのものは止めない。action 候補が
        出ないぶん対人行為が発見されなくなるが、prompt 全体を失うより軽い。
        """
        entries: list[SpotGraphInteractionEntry] = []
        if self._player_action_entries_provider is not None:
            try:
                entries.extend(
                    self._player_action_entries_provider(
                        target_is_incapacitated=is_incapacitated,
                        target_is_eliminated=is_eliminated,
                        actor_state=dict(actor_state or {}),
                        actor_player_id=PlayerId(int(actor_player_id_value))
                        if actor_player_id_value is not None
                        else None,
                        target_is_known_ally=self._resolve_known_ally(
                            actor_player_id_value,
                            target_player_id_value,
                        ),
                    )
                    or ()
                )
            except Exception:
                logger.warning(
                    "player_action_entries_provider が失敗したため、同席者行の"
                    "対人 action 候補を省略する",
                    exc_info=True,
                )
        # 組み込みの対人 tool も同じ行に出す。
        #
        # ここに出るのがシナリオ宣言の interaction だけだと、行の [...] を
        # 「この人にできることの全集合」と読んだエージェントが「take しか
        # 定義されていない」と結論する (v4 第 3 回 run で実際に起きた)。
        # tend_to_player は倒れている相手にしか使えないので、同じ公開事実で
        # ゲートできる。
        # 退場が確定した相手には出さない。engine の普遍則が実行時に必ず弾く
        # ので、出すと「選べるのに必ず失敗する手」になる。旧実装は is_down と
        # is_dead を同じ「行動不能」に畳んでいたため、死体にも手当てが出ていた。
        if (
            is_incapacitated
            and not is_eliminated
            and self._tool_is_exposed(TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER)
        ):
            # シナリオ宣言の interaction は日本語のラベルつきで並ぶのに、
            # engine の tool だけ生の識別子で出ていた。#892 の「engine の
            # 語彙をプロンプトに出さない」に揃える。
            entries.append(
                SpotGraphInteractionEntry(
                    action_name=TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
                    display_label="介抱して起こす",
                )
            )
        return tuple(entries)

    def _resolve_known_ally(
        self,
        actor_player_id_value: int | None,
        target_player_id_value: int | None,
    ) -> bool:
        """表示済みの「同じ側」関係だけを返し、役割語彙は保持しない。"""
        if (
            self._known_ally_checker is None
            or actor_player_id_value is None
            or target_player_id_value is None
        ):
            return False
        try:
            return bool(
                self._known_ally_checker(
                    PlayerId(int(actor_player_id_value)),
                    PlayerId(int(target_player_id_value)),
                )
            )
        except Exception:
            logger.warning(
                "known_ally_checker が失敗したため、相方による候補除外を省略する",
                exc_info=True,
            )
            return False

    def set_object_cooldown_hint_provider(self, provider: Optional[Any]) -> None:
        """物体操作の待ち時間ヒントを後付けで注入する (二段構築用)。"""
        self._object_cooldown_hint_provider = provider

    def set_item_cooldown_hint_provider(self, provider: Optional[Any]) -> None:
        """道具操作の待ち時間ヒントを後付けで注入する。"""
        self._item_cooldown_hint_provider = provider

    def _object_cooldown_hints(self, player_id, obj, interaction) -> tuple:
        """その操作がいま待ち中なら、その断りを 1 つ返す。

        行ごと消さない。消すと**自分の手段そのものを見失う** (#964 と同じ
        判断)。いつ使えるようになるかが書いてあれば、待つという次の手に繋がる。
        """
        if self._object_cooldown_hint_provider is None:
            return ()
        # 例外は握りつぶさない。ここで空に倒すと、配線が壊れたときに
        # **待ちの断りだけが静かに消える**。「いつでも使える」と読める行に
        # 戻り、しかも誰も気付かない (#964 で codex に指摘された形)。
        hint = self._object_cooldown_hint_provider(
            player_id, obj.object_id, interaction
        )
        return (hint,) if hint else ()

    def _item_cooldown_hints(
        self, player_id: PlayerId, item_spec_id: ItemSpecId, interaction: Any
    ) -> tuple[str, ...]:
        """道具操作が待ち中なら、物体操作と同じ形式の断りを返す。"""
        if self._item_cooldown_hint_provider is None:
            return ()
        hint = self._item_cooldown_hint_provider(
            player_id, item_spec_id, interaction
        )
        return (hint,) if hint else ()

    def _tool_is_exposed(self, tool_name: str) -> bool:
        """この世界にそのツールが存在するか。未注入なら出す側に倒す。

        **宣伝する前に必ず通す。** 無効化されたツールを行動候補として並べる
        と、エージェントはそれを選び、存在しないツールを呼ぶ。無効化しない
        より悪い状態になる。

        未注入で出す側に倒すのは、この口を知らない既存の組み立て経路
        (テスト用の直接構築など) の挙動を変えないため。本番経路が必ず
        注入していることは `test_tool_exposure` が固定する。コメントの
        主張だけにしておくと、片方の経路で注入漏れが起きる。

        例外は握らない。**握ると、この PR が直した穴がそのまま戻る。**
        ここが決めるのは「本文で宣伝するか」だけで、ツールの存在そのものは
        `get_tool_definitions` が決める。握った場合の被害は「存在しない
        ツールを宣伝する」、握らない場合は「案内文が 1 行消える」で、
        軽いのは後者。注入されるのは frozenset の照合なので、そもそも
        現実的に例外を投げない。発火するのは配線バグのときだけで、その
        ときに宣伝だけ復活するのは最悪の縮退になる。
        """
        if self._is_tool_exposed is None:
            return True
        return bool(self._is_tool_exposed(tool_name))

    def _build_time_of_day_entry(self) -> Optional[SpotGraphTimeOfDayEntry]:
        """シナリオが昼夜サイクルを宣言していれば snapshot に現在時刻を載せる。

        provider が未設定 (= シナリオが day_night を宣言していない) なら None。
        provider が例外を投げるのは想定外。silent に握りつぶさず warning ログ
        を出した上で None を返し、プロンプトから時刻行を落とす safer fallback
        にする。
        """
        if self._time_of_day_provider is None:
            return None
        try:
            tod = self._time_of_day_provider()
        except Exception:
            logger.warning(
                "time_of_day_provider raised unexpectedly; skipping time_of_day in snapshot",
                exc_info=True,
            )
            return None
        if tod is None:
            return None
        return SpotGraphTimeOfDayEntry(
            phase_name=tod.phase_name,
            display_text=tod.display_text,
            is_dark=tod.is_dark,
        )

    def _resolve_stagnation_band(self, entity_id: int) -> str:
        """entity_id の停滞感バンドを provider から引く。

        provider 未注入 / 例外は常に ``STAGNATION_PRESSURE_BAND_NONE`` に
        縮退させる (= flag OFF や配線漏れで表出が壊れて他の表示まで巻き込む
        事故を防ぐ、既存の time_of_day_provider 等と同じ safer fallback)。
        """
        if self._stagnation_band_provider is None:
            return STAGNATION_PRESSURE_BAND_NONE
        try:
            return self._stagnation_band_provider(entity_id)
        except Exception:
            logger.warning(
                "stagnation_band_provider raised unexpectedly for entity_id=%s; "
                "falling back to none",
                entity_id,
                exc_info=True,
            )
            return STAGNATION_PRESSURE_BAND_NONE

    def set_dead_player_checker(
        self, checker: Optional[Callable[[PlayerId], bool]]
    ) -> None:
        """DEAD 判定 checker を後から差し込む。

        PlayerOutcomeRegistry は create_world_runtime 内で state_builder より
        後に生成されるため、構築時 (dead_player_checker=) では渡せず、registry
        生成後にこの setter で配線する。
        """
        self._dead_player_checker = checker

    def _carried_item_names_of_fallen(
        self, entity_id: int, *, is_incapacitated: bool
    ) -> tuple:
        """行動不能な相手が持っているものの表示名を返す。

        起きて動いている相手には空を返す。持ち物が常時見えると窃盗が作業に
        なって質感が薄れるので、奪う前に倒す必要が生まれる形にする (ユーザ確定)。

        inventory builder が注入されていない構成 (minimal wiring / 一部テスト)
        では空に縮退する。ここは「見せる情報が増えない」だけで、行動が黙って
        失敗する類の縮退ではない。
        """
        if not is_incapacitated or self._inventory_builder is None:
            return ()
        try:
            entries = self._inventory_builder(PlayerId(entity_id))
        except Exception:
            logger.warning(
                "inventory_builder raised while listing carried items of "
                "fallen player entity_id=%s; showing nothing",
                entity_id,
                exc_info=True,
            )
            return ()
        # 数量を併記する。狼煙に流木が何本要るか、という判断に効くため
        # (自分の所持品欄も同じく数量つきで出ている)。
        names: list[str] = []
        seen: set[str] = set()
        for entry in entries or ():
            name = str(getattr(entry, "name", "") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            quantity = getattr(entry, "quantity", 1)
            names.append(f"{name} x{quantity}" if quantity and quantity > 1 else name)
        return tuple(names)

    def _resolve_is_dead(self, entity_id: int) -> bool:
        """entity_id の player が終局 DEAD (復活不可) かを checker から引く。

        checker 未注入 / 例外 / 非 player entity は常に False に縮退させる
        (= 配線漏れで死亡表示が他の表示まで巻き込む事故を防ぐ safer fallback)。
        """
        if self._dead_player_checker is None:
            return False
        try:
            return bool(self._dead_player_checker(PlayerId(entity_id)))
        except Exception:
            logger.warning(
                "dead_player_checker raised unexpectedly for entity_id=%s; "
                "falling back to not-dead",
                entity_id,
                exc_info=True,
            )
            return False

    def _build_distant_view_result(
        self,
        *,
        graph,
        current_spot_id,
    ) -> DistantViewResult:
        """現在地から見える常時遠景を計算する。

        areas 未設定のシナリオは後方互換として何も出さない。計算例外は prompt 全体を
        落とさず warning + skip に倒すが、trace 有効時には理由を残す。
        """
        try:
            spots = tuple(
                DistantViewSpot(
                    spot_id=node.spot_id.value,
                    area_id=node.area_id,
                    x=(node.position.x if node.position is not None else None),
                    y=(node.position.y if node.position is not None else None),
                    is_outdoor=bool(node.is_outdoor),
                )
                for node in graph.iter_spot_nodes()
            )
            areas = tuple(
                DistantViewArea(
                    area_id=str(getattr(area, "area_id")),
                    name=str(getattr(area, "name", "")),
                    visible_name=str(getattr(area, "visible_name", "")),
                    prominence=float(getattr(area, "prominence", 0.0)),
                    x=(
                        getattr(getattr(area, "position", None), "x", None)
                    ),
                    y=(
                        getattr(getattr(area, "position", None), "y", None)
                    ),
                    distant_descriptions=dict(
                        getattr(area, "distant_descriptions", {}) or {}
                    ),
                )
                for area in self._areas
            )
            active_cues, cue_skipped_reasons = self._resolve_active_distant_cues(
                graph=graph,
                areas_by_id={area.area_id: area for area in areas},
            )
            connections = tuple(
                DistantViewConnection(
                    from_spot_id=conn.from_spot_id.value,
                    to_spot_id=conn.to_spot_id.value,
                )
                for conn in graph.iter_outgoing_connections_from(current_spot_id)
            )
            return self._distant_view_service.render(
                current_spot_id=current_spot_id.value,
                spots=spots,
                areas=areas,
                connections=connections,
                cues=active_cues,
            ).with_added_skipped_reasons(cue_skipped_reasons)
        except Exception:
            logger.warning(
                "distant view calculation failed for spot_id=%s; skipping",
                getattr(current_spot_id, "value", current_spot_id),
                exc_info=True,
            )
            return DistantViewResult(lines=(), skipped_reasons=("calculation_failed",))

    def _resolve_active_distant_cues(
        self,
        *,
        graph,
        areas_by_id: Mapping[str, DistantViewArea],
    ) -> tuple[tuple[DistantViewCandidate, ...], tuple[str, ...]]:
        """scenario.distant_cues から現在 active な遠景候補を解決する。"""
        active: list[DistantViewCandidate] = []
        skipped: set[str] = set()
        for cue in self._distant_cues:
            cue_id = str(getattr(cue, "cue_id", "<unknown>"))
            source = getattr(cue, "source", None)
            if source is None or getattr(source, "kind", None) != "object_state":
                logger.warning(
                    "distant cue source kind is unsupported at runtime: cue_id=%s",
                    cue_id,
                )
                skipped.add("cue_source_unsupported")
                continue
            try:
                object_id = getattr(source, "object_id")
                obj = self._find_spot_object(graph, object_id)
            except Exception:
                logger.warning(
                    "distant cue source object resolution failed: cue_id=%s",
                    cue_id,
                    exc_info=True,
                )
                skipped.add("cue_source_resolution_failed")
                continue
            if obj is None:
                logger.warning(
                    "distant cue source object is missing: cue_id=%s",
                    cue_id,
                )
                skipped.add("cue_source_object_missing")
                continue
            state_key = str(getattr(source, "state_key", ""))
            if obj.state.get(state_key) != getattr(source, "equals", None):
                continue
            origin_area_id = str(getattr(cue, "origin_area_id", ""))
            area = areas_by_id.get(origin_area_id)
            if area is None:
                logger.warning(
                    "distant cue origin area is missing: cue_id=%s area_id=%s",
                    cue_id,
                    origin_area_id,
                )
                skipped.add("cue_origin_area_missing")
                continue
            active.append(
                DistantViewCandidate(
                    candidate_id=cue_id,
                    kind="cue",
                    visible_name=str(getattr(cue, "visible_name", "")),
                    prominence=float(getattr(cue, "prominence", 0.0)),
                    x=area.x,
                    y=area.y,
                    descriptions=dict(
                        getattr(cue, "ambient_descriptions", {}) or {}
                    ),
                    origin_area_id=origin_area_id,
                )
            )
        return tuple(active), tuple(sorted(skipped))

    def _find_spot_object(self, graph, object_id: Any):  # noqa: ANN001, ANN201
        """全 spot の interior から object_id に一致する object を探す。"""
        if not isinstance(object_id, SpotObjectId):
            object_id = SpotObjectId.create(int(getattr(object_id, "value", object_id)))
        for node in graph.iter_spot_nodes():
            interior = self._spot_interior_repository.find_by_spot_id(node.spot_id)
            if interior is None:
                continue
            obj = interior.get_object(object_id)
            if obj is not None:
                return obj
        return None

    def _record_distant_view_trace(
        self,
        *,
        player_id: int,
        spot_id: int,
        current_area_id: Optional[str],
        result: DistantViewResult,
    ) -> None:
        """遠景の現在状態系 trace を明示フラグ有効時だけ記録する。"""
        if not self._distant_view_trace_enabled:
            return
        if self._trace_recorder_provider is None:
            return
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        tick: Optional[int] = None
        if self._current_tick_provider is not None:
            try:
                tick = int(self._current_tick_provider())
            except Exception:
                tick = None
        try:
            from ai_rpg_world.application.trace import TraceEventKind

            kind = (
                TraceEventKind.DISTANT_VIEW_RENDERED
                if result.lines
                else TraceEventKind.DISTANT_VIEW_SKIPPED
            )
            recorder.record(
                kind,
                tick=tick,
                player_id=player_id,
                spot_id=spot_id,
                current_area_id=current_area_id,
                candidate_count=result.candidate_count,
                rendered_count=len(result.lines),
                rendered_area_ids=list(result.rendered_area_ids),
                rendered_cue_ids=list(result.rendered_cue_ids),
                active_cue_count=result.active_cue_count,
                skipped_reasons=list(result.skipped_reasons),
                thresholds={
                    "prominence": self._distant_view_service.prominence_threshold,
                    "score": self._distant_view_service.score_threshold,
                    "outdoor_visibility_range": (
                        self._distant_view_service.outdoor_visibility_range
                    ),
                    "max_lines": self._distant_view_service.max_lines,
                },
            )
        except Exception:
            logger.warning(
                "DISTANT_VIEW trace record failed for player_id=%s spot_id=%s; skipping",
                player_id,
                spot_id,
                exc_info=True,
            )

    def _notify_visible_monsters(
        self,
        player_id: int,
        monsters_at_spot: Sequence[SpotGraphMonsterEntry],
    ) -> None:
        """snapshot に見えている monster を観測 hook へ渡す。

        初回判定や observation 生成は runtime 側の責務にし、builder は
        「肉眼で見えた」という事実だけを通知する。hook の失敗で prompt
        構築を壊さないよう、例外は warning に落とす。
        """
        observer = self._visible_monster_observer
        if observer is None:
            return
        for entry in monsters_at_spot:
            try:
                observer(player_id, entry)
            except Exception:
                logger.warning(
                    "visible_monster_observer failed for player_id=%s monster_id=%s",
                    player_id,
                    entry.monster_id,
                    exc_info=True,
                )

    def _notify_fallen_bodies(
        self,
        player_id: int,
        nearby_entities: Sequence[SpotGraphNearbyEntityEntry],
    ) -> None:
        """同じ場所で倒れている人を観測 hook へ渡す。

        **同席者行に出ているのに、気づいた瞬間が無かった。** 行は「見えて
        いる状態」で、毎 tick そこにある。観測は「気づいた瞬間」で一度きり。
        両方要る。観測が無いと ``schedules_turn`` が立たず、死体を見つけても
        エージェントが起きない (run 008 で通報が始まらなかった直接の原因)。

        暗さは見ない。同席者行が暗所でも死体を出しているので、ここだけ
        隠すと**行と観測が食い違う**。

        monster と同じく、初回判定は runtime 側。hook の失敗で prompt 構築を
        壊さないよう、例外は warning に落とす。
        """
        observer = self._fallen_body_observer
        if observer is None:
            return
        for entry in nearby_entities:
            if int(entry.entity_id) == int(player_id):
                # 自分の亡骸は現在状態として見せるが、「他者の身体を初めて
                # 見つけた」という一度きり観測にはしない。
                continue
            if not (entry.is_down or entry.is_dead):
                continue
            try:
                observer(
                    player_id,
                    int(entry.entity_id),
                    str(entry.display_name or ""),
                    bool(entry.is_dead),
                )
            except Exception:
                logger.warning(
                    "fallen_body_observer failed for player_id=%s entity_id=%s",
                    player_id,
                    entry.entity_id,
                    exc_info=True,
                )

    def build_snapshot(self, player_id: int) -> SpotGraphPlayerSnapshotDto | None:
        """生者は物理グラフ、幽霊は別位置 store から現在地を解決する。"""
        graph = self._spot_graph_repository.find_graph()
        eid = EntityId.create(player_id)
        viewer_player_id = PlayerId(player_id)
        viewer_is_departed = bool(
            self._player_perception_policy is not None
            and self._player_perception_policy.is_departed(viewer_player_id)
        )
        viewer_plane = (
            InteractionActorPlane.DEPARTED
            if viewer_is_departed
            else InteractionActorPlane.LIVING
        )
        if viewer_is_departed:
            spot_id = (
                self._departed_position_store.find(viewer_player_id)
                if self._departed_position_store is not None
                else None
            )
            if spot_id is None:
                return None
        else:
            try:
                spot_id = graph.get_entity_spot(eid)
            except EntityNotInGraphException:
                return None

        node = graph.get_spot(spot_id)
        current_tick: Optional[int] = None
        if self._current_tick_provider is not None:
            try:
                current_tick = int(self._current_tick_provider())
            except Exception:
                logger.warning(
                    "current_tick_provider raised unexpectedly; "
                    "stock condition hints use recorded stock_tick",
                    exc_info=True,
                )
        player = self._player_status_repository.find_by_id(PlayerId(player_id))
        travel_line: str | None = None
        agent_status = SpotGraphAgentStatusEntry()
        if player is not None and player.spot_navigation_state is not None:
            nav = player.spot_navigation_state
            if nav.is_traveling:
                dest = nav.route[-1] if nav.route else spot_id
                dest_name = graph.get_spot(dest).name
                # 残り tick の概算: 現区間 + 未消化区間の合計
                remaining = nav.ticks_remaining_on_current_leg
                for idx in range(nav.leg_index + 1, len(nav.leg_travel_ticks)):
                    remaining += nav.leg_travel_ticks[idx]
                travel_line = (
                    f"スポット間移動中（残り合計 {remaining} tick）"
                    f" → 目的地: {dest_name}"
                )
                agent_status = SpotGraphAgentStatusEntry(
                    busy=True,
                    busy_reason=f"{dest_name} への移動中",
                    remaining_ticks=remaining,
                    interruptible=True,
                )

        connections: list[SpotGraphConnectionEntry] = []
        connection_lines: list[str] = []
        for conn in graph.iter_outgoing_connections_from(spot_id):
            dest = graph.get_spot(conn.to_spot_id)
            traversable = conn.passage.traversable
            condition_text: str | None = None
            if not traversable:
                if conn.passage_conditions:
                    msgs = [pc.failure_message for pc in conn.passage_conditions if pc.failure_message]
                    condition_text = "；".join(msgs) if msgs else None
                if not condition_text and conn.description:
                    condition_text = conn.description
            connections.append(SpotGraphConnectionEntry(
                destination_spot_id=conn.to_spot_id.value,
                connection_name=conn.name,
                destination_spot_name=dest.name,
                is_passable=traversable,
                passage_condition_text=condition_text,
            ))
            status = "通行可" if traversable else "通行不可（音は届く可能性あり）"
            connection_lines.append(f"- {conn.name} → {dest.name}（{status}）")

        distant_view_result = self._build_distant_view_result(
            graph=graph,
            current_spot_id=spot_id,
        )
        self._record_distant_view_trace(
            player_id=player_id,
            spot_id=spot_id.value,
            current_area_id=node.area_id,
            result=distant_view_result,
        )

        objects: list[SpotGraphObjectEntry] = []
        dark_hidden_object_names: list[str] = []
        sub_locations: list[SpotGraphSubLocationEntry] = []
        sub_lines: list[str] = []
        obj_lines: list[str] = []
        ground_lines: list[str] = []
        ground_items: list[SpotGraphGroundItemEntry] = []

        # --- 知覚判定: 照明 + 光源 ---
        # 実効照明の算出は SpotEffectiveLightingResolver に集約する。
        # SPOT_LIGHTING_IS の判定も同じ resolver を使うので、prompt の「暗い」
        # と前提条件の「暗い」が食い違わない。
        presence = graph.presence_at(spot_id)
        viewer_has_light = self._entity_has_light_source(player_id)
        spot_has_any_light_bearer = viewer_has_light or any(
            self._entity_has_light_source(int(other_eid))
            for other_eid in presence.present_entity_ids
            if other_eid != eid
        )
        # resolve() が None を返すのは「その spot が graph に無い」場合だけ。
        # ここは spot から node を引けている文脈なので実際には起きないが、
        # 型としては Optional なので atmosphere 未宣言と同じ BRIGHT に倒す。
        # 想定外の失敗は resolve() が例外のまま上げる (握りつぶすと表示は
        # 「明るい」・前提条件は「暗くない」に食い違って倒れる)。
        effective_lighting = (
            self._lighting_resolver.resolve(spot_id) or LightingEnum.BRIGHT
        )
        can_see = self._perception.can_see_objects(effective_lighting)

        # 光源持ちの名前を解決（知覚テキスト用）
        light_bearer_name: str | None = None
        if not viewer_has_light and spot_has_any_light_bearer and self._entity_name_resolver:
            for other_eid in presence.present_entity_ids:
                if other_eid != eid and self._entity_has_light_source(int(other_eid)):
                    try:
                        light_bearer_name = self._entity_name_resolver(int(other_eid))
                    except Exception:
                        light_bearer_name = None
                    break

        interior = self._spot_interior_repository.find_by_spot_id(spot_id)
        current_sub_id = (
            player.spot_navigation_state.current_sub_location_id
            if player is not None and player.spot_navigation_state is not None
            else None
        )
        if interior is not None:
            world_flags = (
                self._world_flags_provider() if self._world_flags_provider is not None else frozenset()
            )
            for sl in interior.sub_locations:
                is_current = current_sub_id is not None and current_sub_id == sl.sub_location_id
                sub_locations.append(SpotGraphSubLocationEntry(
                    sub_location_id=sl.sub_location_id.value,
                    name=sl.name,
                    is_current=is_current,
                    is_hidden=sl.is_hidden,
                ))
                here = "（現在ここ）" if is_current else ""
                hidden = "（未発見）" if sl.is_hidden else ""
                sub_lines.append(f"- {sl.name}{here}{hidden}")

            for obj in interior.objects:
                if not obj.is_visible:
                    continue
                if not can_see and not obj.is_visible_in_dark:
                    dark_hidden_object_names.append(obj.name)
                    continue
                # P0-1/4b: OBJECT_STATE / OBJECT_STOCK_AT_LEAST が現在失敗
                # していても action は落とさない。落とすと「操作名一覧が空
                # なのに説明は操作を誘う」状態になり、LLM が存在しない
                # action_name を発明する。代わりに blocking_hints として
                # 分け、候補集合を保ったまま「今は通らない理由」を見せる。
                interactions = tuple(
                    SpotGraphInteractionEntry(
                        action_name=i.action_name,
                        display_label=i.display_label,
                        condition_hints=_interaction_condition_hints(
                            i,
                            interior,
                            self._time_of_day_phase_label_resolver,
                        ) + self._object_cooldown_hints(player_id, obj, i),
                        blocking_hints=_interaction_blocking_hints(
                            i,
                            interior,
                            current_tick=current_tick,
                        ),
                    )
                    # 役割・世界状態・存在層で弾かれる候補は、blocked にも
                    # 回さず丸ごと落とす。救済一覧も同じ集合を参照する。
                    for i in visible_interactions_for_actor_plane(
                        obj.interactions, player, world_flags, viewer_plane
                    )
                )
                # Phase 4-E: スポットに居る全員から見える state を載せる。
                # hidden な記録手番は、生値を伏せたまま current_tick と実効照明
                # から作者文言へ変換する。規則評価は visible_state() に集約し、
                # builder 側で同じ条件を組み直さない。
                visible_state = obj.visible_state(
                    current_tick=current_tick,
                    effective_lighting=effective_lighting,
                    world_flags=world_flags,
                    minutes_per_tick=self._minutes_per_tick,
                )
                objects.append(SpotGraphObjectEntry(
                    object_id=obj.object_id.value,
                    name=obj.name,
                    description=obj.resolved_description(
                        world_flags, viewer_entity_id=player_id
                    ),
                    interactions=interactions,
                    has_actor_hidden_interactions=(
                        bool(obj.interactions) and not interactions
                    ),
                    # 役割・世界状態だけで判定した集合。これが空なら、
                    # **落ちた理由は本人の職能や世界の状態**であって
                    # 存在層ではない。理由ごとに見せてよいものが違うので
                    # 分けて持つ。
                    has_role_hidden_interactions=(
                        bool(obj.interactions)
                        and not visible_interactions(
                            obj.interactions, player, world_flags
                        )
                    ),
                    unreachable_attribute_notes=unreachable_attribute_notes(
                        obj.interactions,
                        getattr(player, "state", None),
                        self._player_attribute_specs,
                    ),
                    state=visible_state,
                ))
                # フォールバック行 (interactions DTO と整合): 同じヒント分離を
                # 使い、失敗 action も「いまできない」として残す。
                # 伏せる操作はここでも落とす。**上の DTO 側だけ絞って
                # いた。** 一覧を作る側は必ず同じ判断を通す
                # (hidden_interaction_filter)。
                actions = [
                    _format_interaction_action_name_with_hints(
                        i,
                        interior,
                        current_tick=current_tick,
                        phase_label_resolver=self._time_of_day_phase_label_resolver,
                    )
                    for i in visible_interactions_for_actor_plane(
                        obj.interactions, player, world_flags, viewer_plane
                    )
                ]
                act = " / ".join(actions) if actions else "—"
                obj_lines.append(f"- {obj.name} [ {act} ]")

            if can_see:
                for gi in interior.ground_items:
                    name = ""
                    if self._item_spec_name_resolver is not None:
                        try:
                            name = self._item_spec_name_resolver(gi.item_spec_id.value)
                        except Exception:
                            name = ""
                    if not name:
                        name = f"アイテム#{gi.item_instance_id.value}"
                    is_spoiled = False
                    if self._item_state_resolver is not None:
                        try:
                            state = self._item_state_resolver(gi.item_instance_id.value)
                            if state is not None:
                                is_spoiled = bool(state.get("spoiled"))
                        except Exception:
                            # resolver の例外は表示用なので silent fallback (False)。
                            # 永続的バグは観測 callback 経由でログに出るので、
                            # 表示パスで握り潰しても二重隠蔽にはならない。
                            is_spoiled = False
                    ground_items.append(SpotGraphGroundItemEntry(
                        item_instance_id=gi.item_instance_id.value,
                        item_spec_id=gi.item_spec_id.value,
                        name=name,
                        is_spoiled=is_spoiled,
                    ))
                    # 後方互換: 旧 ground_item_lines に名前付き行を残す。
                    ground_lines.append(f"- {name}")

        atmosphere: SpotGraphAtmosphereEntry | None = None
        if node.atmosphere is not None:
            a = node.atmosphere
            base_lighting = a.lighting
            perception_note = self._perception.describe_lighting_perception(
                base_lighting, effective_lighting, viewer_has_light, light_bearer_name
            )
            atmosphere = SpotGraphAtmosphereEntry(
                lighting=effective_lighting.name,
                sound_ambient=a.sound_ambient,
                temperature=a.temperature.name,
                smell=a.smell,
                perception_note=perception_note,
            )

        # スポットに居るモンスター個体。`can_see` が False（暗闇）の場合は
        # オブジェクトと同じく完全に隠す。
        # TODO(combat-pr): 暗闇では「攻撃されているのに current_state に居ない」
        # 状態が起き得る。戦闘ツール導入と同じ PR で「気配がする / うなり声」
        # の縮退表記に拡張する。それまでは戦闘ツールが入る前提なので gameplay
        # 上の不整合は発生しない（モンスターは行動できないため）。
        monsters_at_spot: list[SpotGraphMonsterEntry] = []
        if can_see and self._monster_view_provider is not None:
            monster_presence = graph.monster_presence_at(spot_id)
            for monster_id in sorted(
                monster_presence.present_monster_ids, key=lambda m: m.value
            ):
                view = self._monster_view_provider(monster_id)
                if view is None:
                    # 通常はターン中の race（aggregate と presence の一時的な
                    # 不整合）で None になり得るため、例外ではなく黙って除外
                    # する。ただし観測性のため debug ログだけは残す。バグ起因
                    # の不整合（presence に残り続ける monster_id）も同パスを
                    # 通るので、ログ無しでは追跡が難しくなる。
                    logger.debug(
                        "monster_view_provider returned None for monster_id=%s at spot_id=%s",
                        monster_id.value,
                        spot_id.value,
                    )
                    continue
                monsters_at_spot.append(view)
        self._notify_visible_monsters(player_id, monsters_at_spot)

        nearby_entities: list[SpotGraphNearbyEntityEntry] = []
        own_body = self._fallen_body_registry.find(viewer_player_id)
        if (
            viewer_is_departed
            and own_body is not None
            and own_body.spot_id == spot_id
        ):
            own_name = ""
            if self._entity_name_resolver is not None:
                try:
                    own_name = self._entity_name_resolver(player_id)
                except Exception:
                    own_name = f"不明({player_id})"
            nearby_entities.append(
                SpotGraphNearbyEntityEntry(
                    entity_id=player_id,
                    display_name=own_name,
                    is_down=True,
                    is_dead=True,
                    is_own_fallen_body=True,
                    action_entries=(),
                )
            )
        entity_ids = list(presence.present_entity_ids)
        if self._departed_position_store is not None:
            entity_ids.extend(
                EntityId.create(int(departed_player_id))
                for departed_player_id in self._departed_position_store.players_at(
                    spot_id
                )
                if EntityId.create(int(departed_player_id)) not in entity_ids
            )
        departed_entity_ids_here = {
            EntityId.create(int(departed_player_id))
            for departed_player_id in (
                self._departed_position_store.players_at(spot_id)
                if self._departed_position_store is not None
                else ()
            )
        }
        entity_ids.extend(
            EntityId.create(int(record.player_id))
            for record in self._fallen_body_registry.records_at(spot_id)
            if EntityId.create(int(record.player_id)) not in entity_ids
        )
        for other_eid in entity_ids:
            if other_eid != eid:
                body = self._fallen_body_registry.find(PlayerId(int(other_eid)))
                body_is_here = body is not None and body.spot_id == spot_id
                if (
                    not body_is_here
                    and self._player_perception_policy is not None
                    and not self._player_perception_policy.can_perceive_player(
                        PlayerId(player_id), PlayerId(int(other_eid))
                    )
                ):
                    continue
                if (
                    other_eid not in departed_entity_ids_here
                    and body is not None
                    and body.spot_id != spot_id
                ):
                    # 行為主体が別の場所へ移っても、身体は倒れた場所に残る。
                    continue
                name = ""
                if self._entity_name_resolver is not None:
                    try:
                        name = self._entity_name_resolver(int(other_eid))
                    except Exception:
                        name = f"不明({int(other_eid)})"
                # PR #347 後続: 同 spot にいる相手が倒れているなら snapshot に
                # is_down=True を立てる。entity が player でない (NPC 等) ときや
                # status_repo で見つからないときは False のままにする。
                # PR β (実験 #29 後続): あわせて fatigue_level も lift し、
                # 「(疲れている)」「(ぐったりしている)」を nearby_entities に
                # 常時表示できるようにする。仲間の状態を Observation でなく
                # state として見えるモデル (docs/design_decisions.md #8 参照)。
                other_is_down = False
                other_fatigue_level = "ok"
                try:
                    other_status = self._player_status_repository.find_by_id(
                        PlayerId(int(other_eid))
                    )
                    if other_status is not None:
                        other_is_down = body_is_here
                        # fatigue_level プロパティが無い古い aggregate も想定し getattr で防御
                        other_fatigue_level = getattr(
                            other_status, "fatigue_level", "ok"
                        )
                except Exception:
                    other_is_down = body_is_here
                    other_fatigue_level = "ok"
                # P-U4 (停滞感の表出・他者): fatigue_level と対称に、同 spot の
                # 他 player の停滞感バンドも常時 state として lift する。
                other_stagnation_band = self._resolve_stagnation_band(int(other_eid))
                # 終局 DEAD かを checker で判定 (未注入なら False)。表示で
                # 「(死亡している)」を「(倒れて動かない)」と区別するために使う。
                other_is_dead = self._resolve_is_dead(int(other_eid))
                nearby_entities.append(SpotGraphNearbyEntityEntry(
                    entity_id=int(other_eid),
                    display_name=name,
                    is_down=other_is_down,
                    is_dead=other_is_dead,
                    fatigue_level=other_fatigue_level,
                    stagnation_band=other_stagnation_band,
                    carried_item_names=self._carried_item_names_of_fallen(
                        int(other_eid),
                        is_incapacitated=other_is_down or other_is_dead,
                    ),
                    action_entries=(
                        ()
                        if viewer_is_departed
                        else self._resolve_player_action_entries(
                            is_incapacitated=other_is_down or other_is_dead,
                            is_eliminated=other_is_dead,
                            actor_state=getattr(player, "state", None),
                            actor_player_id_value=int(player_id),
                            target_player_id_value=int(other_eid),
                        )
                    ),
                ))

        self._notify_fallen_bodies(player_id, nearby_entities)

        inventory_items: tuple[SpotGraphInventoryItemEntry, ...] = ()
        if self._inventory_builder is not None:
            inventory_items = self._inventory_builder(PlayerId(player_id))
            from dataclasses import replace

            enriched_inventory_items: list[SpotGraphInventoryItemEntry] = []
            for entry in inventory_items:
                declared = self._item_interaction_registry.interactions_for(
                    ItemSpecId.create(entry.item_spec_id)
                )
                visible = tuple(
                    SpotGraphInteractionEntry(
                        action_name=interaction.action_name,
                        display_label=interaction.display_label,
                        condition_hints=_interaction_condition_hints(
                            interaction, interior,
                            self._time_of_day_phase_label_resolver,
                        ),
                        blocking_hints=_interaction_blocking_hints(
                            interaction,
                            interior,
                            current_tick=current_tick,
                        )
                        + self._item_cooldown_hints(
                            player_id,
                            ItemSpecId.create(entry.item_spec_id),
                            interaction,
                        ),
                    )
                    for interaction in visible_interactions_for_actor_plane(
                        declared, player, world_flags, viewer_plane
                    )
                )
                enriched_inventory_items.append(
                    replace(
                        entry,
                        interactions=visible,
                    )
                )
            inventory_items = tuple(enriched_inventory_items)

        weather: SpotGraphWeatherEntry | None = None
        if node.is_outdoor and self._weather_provider is not None:
            ws = self._weather_provider()
            if ws is not None:
                weather = SpotGraphWeatherEntry(
                    weather_type=ws.weather_type.value,
                    weather_intensity=ws.intensity,
                    is_outdoor=True,
                )

        # エージェントの欲求状態
        # PR-T: 前 turn からの delta を併記する。compute_need_deltas() は
        # 副作用なし (= snapshot は別経路で取る)。snapshot は
        # ``snapshot_needs_for_delta_after_prompt_build`` で本 build の末尾に
        # 呼ぶ (= 「prompt build 完了直前」を次回 baseline にする)。
        need_lines: tuple[str, ...] = ()
        need_states: tuple = ()
        hp_line: str = ""
        if player is not None:
            deltas = player.compute_need_deltas()
            need_lines = player.needs.describe_all_with_deltas(deltas)
            # 表示文とは別に欲求そのものを渡す。想起の検索語は値から決める
            # (以前は need_lines を文字列として読み直していた / 系統2)。
            need_states = tuple(player.needs)
            # HP を need と同じ「身体の状態」section に、値 + 前 turn からの
            # 増減つきで出す。baseline の snapshot は need と同じく prompt build
            # 完了直前 (runtime_manager) で snapshot_hp_for_delta() を呼ぶ。
            hp_line = player.hp.describe(player.compute_hp_delta())

        # PR #2 状態異常 surface: active_effects を「出血 (残り 9 tick)」のような
        # 表記に変換して snapshot に載せる。current_tick_provider が未注入なら
        # 残り tick を省略する fallback (effect 名のみ)。
        active_effect_lines: tuple[str, ...] = ()
        if player is not None and player.active_effects:
            active_effect_lines = self._build_active_effect_lines(
                player.active_effects
            )

        # Phase 4-E: 行動者本人の自由 state を snapshot に載せる。HIDDEN を
        # 含む全項目を本人プロンプトに渡し、自己認識させる。第三者用の
        # snapshot は別経路 (recipient strategy + 専用 event) なのでここでは
        # 全部載せて問題ない。
        player_state_snapshot: dict = (
            dict(player.state) if player is not None else {}
        )
        # 本人の疲労 tier を専用 field に lift。ui_context_builder が「身体の
        # 状態」section の hint (= exhausted で重い tool が block されている等)
        # を出すために参照する。旧構造では ``player_state["fatigue_level"]``
        # で取ろうとしていたが ``player_state`` は ``dict(player.state)`` (=
        # 自由 state) しか乗らず常に None になっていた silent failure を解消。
        own_fatigue_level: str = (
            getattr(player, "fatigue_level", "ok") if player is not None else "ok"
        )
        # P-U3 (停滞感の表出・自己): own_fatigue_level と対称に本人の停滞感
        # バンドを lift する。
        own_stagnation_band: str = self._resolve_stagnation_band(player_id)

        return SpotGraphPlayerSnapshotDto(
            current_spot_id=spot_id.value,
            current_spot_name=node.name,
            current_spot_description=node.description,
            travel_status_line=travel_line,
            viewer_is_departed=viewer_is_departed,
            distant_view_lines=distant_view_result.lines,
            connections=tuple(connections),
            objects=tuple(objects),
            dark_hidden_object_names=tuple(dark_hidden_object_names),
            sub_locations=tuple(sub_locations),
            atmosphere=atmosphere,
            weather=weather,
            nearby_entities=tuple(nearby_entities),
            state_display_names=self._state_display_names,
            hidden_player_state_keys=self._hidden_player_state_keys,
            can_give_item=(
                not viewer_is_departed
                and self._tool_is_exposed(TOOL_NAME_SPOT_GRAPH_GIVE_ITEM)
            ),
            monsters_at_spot=tuple(monsters_at_spot),
            inventory_items=inventory_items,
            ground_items=tuple(ground_items),
            time_of_day=self._build_time_of_day_entry(),
            need_lines=need_lines,
            need_states=need_states,
            hp_line=hp_line,
            ground_item_lines=ground_lines,
            connection_lines=connection_lines,
            sub_location_lines=sub_lines,
            object_lines=obj_lines,
            player_state=player_state_snapshot,
            active_effect_lines=active_effect_lines,
            agent_status=agent_status,
            own_fatigue_level=own_fatigue_level,
            own_stagnation_band=own_stagnation_band,
            economy_declared=bool(self._merchants),
            merchants_at_spot=self._merchant_entries_at(spot_id),
            own_gold=(
                int(player.gold.value) if player is not None and self._merchants else 0
            ),
            incoming_trade_offers=self._incoming_trade_offers(player_id),
            market_declared=self._market_service is not None
            and getattr(self._market_service, "board_spot_id", None) is not None,
            market_board_here=self._is_at_the_board(spot_id),
            market_reaches_everywhere=self._market_reaches_everywhere(),
            market_board_spot_name=self._board_spot_name(graph),
            market_own_orders=self._market_own_orders(player_id, spot_id),
        )

    def _incoming_trade_offers(self, player_id: int) -> tuple:
        """自分宛てに来ている申し出を表示用に整える。"""
        if self._incoming_trade_offers_provider is None:
            return ()
        try:
            return tuple(self._incoming_trade_offers_provider(player_id))
        except Exception:
            logger.warning(
                "自分宛ての取引の申し出を組み立てられませんでした", exc_info=True
            )
            return ()

    def _is_at_the_board(self, spot_id: SpotId) -> bool:
        """その場所に市場の掲示板があるか。"""
        if self._market_service is None:
            return False
        return getattr(self._market_service, "board_spot_id", None) == spot_id

    def _market_reaches_everywhere(self) -> bool:
        """板がどこからでも届くか。"""
        reach = getattr(self._market_service, "reach", None)
        return bool(reach is not None and reach.is_global)

    def _board_spot_name(self, graph: Any) -> str:
        """板が物として在る場所の名前。

        届く世界でも要る。受け取れなかった品は板の足元に置かれ、**それは
        自分が一度も行っていない場所**になりうる。取りに行くには名前が要る。
        """
        board_spot_id = getattr(self._market_service, "board_spot_id", None)
        if board_spot_id is None:
            return ""
        try:
            return graph.get_spot(board_spot_id).name
        except Exception:  # noqa: BLE001
            return ""

    def _market_own_orders(self, player_id: PlayerId, spot_id: SpotId) -> tuple:
        """自分が板に出している注文を 1 件ずつ返す。

        **他人の注文はここでは作らない。** 板を読むのは `market_view` の仕事で、
        1 手番を払う。自分の注文だけ常駐に残すのは、外すと預けた品がどこからも
        見えなくなるため — 値を変える・取り下げる手がかりが消え、引き取り待ちの
        品も取り戻せなくなる (静かな失敗)。
        """
        if not self._is_at_the_board(spot_id) and not self._market_reaches_everywhere():
            return ()
        from ai_rpg_world.application.llm.services.market_board_text import (
            market_entries_from_view,
        )
        from ai_rpg_world.domain.trade.value_object.market_participant import (
            MarketParticipant,
        )

        view = self._market_service.board().rows_for(
            MarketParticipant.player(player_id)
        )
        _, own_orders = market_entries_from_view(view, self._item_display_name)
        return own_orders

    def _item_display_name(self, item_spec_id: int) -> str:
        """品名を表示名で引く。引けない品は識別子ではなく畳んだ名前にする。"""
        if self._item_spec_name_resolver is None:
            return "(名前不明のもの)"
        try:
            return self._item_spec_name_resolver(int(item_spec_id)) or "(名前不明のもの)"
        except Exception:  # noqa: BLE001
            return "(名前不明のもの)"

    def _merchant_entries_at(self, spot_id: SpotId) -> tuple:
        """現在地に居る商人を表示用データへ変換する。

        品名は item_spec の表示名で出す。解決できない item_spec は行ごと落とす
        のではなく、識別子を出さないため「(名前不明のもの)」に畳む — 価格表の
        件数が黙って減ると、シナリオ作家は表示の欠落に気付けない。
        """
        entries = []
        for merchant in self._merchants:
            if merchant.spot_id != spot_id:
                continue
            entries.append(SpotGraphMerchantEntry(
                merchant_id=merchant.merchant_id,
                name=merchant.name,
                sells=self._merchant_price_entries(merchant.sells),
                buys=self._merchant_price_entries(merchant.buys),
            ))
        return tuple(entries)

    def _merchant_price_entries(self, price_list: Sequence[Any]) -> tuple:
        """価格表 1 本を、品名で引いた表示用データへ変換する。"""
        entries = []
        for price_entry in price_list:
            name = ""
            if self._item_spec_name_resolver is not None:
                try:
                    name = self._item_spec_name_resolver(price_entry.item_spec_id)
                except Exception:
                    name = ""
            entries.append(SpotGraphMerchantPriceEntry(
                item_name=name or "(名前不明のもの)",
                price=price_entry.price,
                item_spec_id=price_entry.item_spec_id,
            ))
        return tuple(entries)

    def _build_active_effect_lines(self, active_effects) -> tuple[str, ...]:
        """active_effects を「<日本語名> (残り N tick)」形式の行に変換する。

        current_tick_provider が未注入なら残り tick を省略する。
        provider が例外を投げた場合は warning log を出して残り tick を省略
        (snapshot 生成全体を落とさない安全側 fallback)。
        """
        current_tick: Optional[int] = None
        if self._current_tick_provider is not None:
            try:
                current_tick = int(self._current_tick_provider())
            except Exception:
                logger.warning(
                    "current_tick_provider raised unexpectedly; "
                    "omitting remaining-tick in active_effect_lines",
                    exc_info=True,
                )
                current_tick = None
        lines: list[str] = []
        for effect in active_effects:
            label = _STATUS_EFFECT_LABELS.get(
                effect.effect_type.value, effect.effect_type.value
            )
            if current_tick is not None:
                remaining = effect.expiry_tick.value - current_tick
                if remaining <= 0:
                    # まもなく cleanup される effect。最後の tick も surface する。
                    lines.append(f"{label} (まもなく治る)")
                else:
                    lines.append(f"{label} (残り {remaining} tick)")
            else:
                lines.append(label)
        return tuple(lines)

    def _entity_has_light_source(self, entity_id: int) -> bool:
        """エンティティが光源アイテムを持っているかを判定する。"""
        if not self._light_source_item_spec_ids:
            return False
        if self._owned_item_spec_ids_provider is None:
            return False
        owned = self._owned_item_spec_ids_provider(entity_id)
        return bool(self._light_source_item_spec_ids & owned)
