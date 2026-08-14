"""SynchronizedActionGroup の毎 tick 解決ステージ。

各 tick の終わりに sync group ごとに以下を判定する:
- 全 required_action_names が prepare 済みかつ全 prepare が窓内 →
  on_complete 効果を発火、関係 prepare flags をクリア
- いずれかの prepare が窓を超過 → on_timeout 効果を発火、関係 prepare
  flags をクリア（部分的な prepare があった場合のみ。何も prepare されて
  いないなら何もしない）

prepare 観測（誰かが prepare したことの通知）はこのステージではなく、
prepare_action ツール側で即時に publish される。

SHOW_MESSAGE は完成・時間切れのどちらでも、実際に prepare した参加者へ
結果観測として届ける。group は場所を持たないため、非参加者へ世界横断で
知らせることはしない。

サポート effect:
on_complete / on_timeout で実用的に動くのは SET_FLAG / CLEAR_FLAG /
CHANGE_PASSAGE_STATE / SHOW_MESSAGE。CHANGE_OBJECT_STATE /
GIVE_ITEM 等は interior が必要だが、resolver は特定のスポットに
紐付かないため non-functional（warning ログのみ）。
"""

from __future__ import annotations

import logging
from typing import Callable, Iterable, List, Literal, Set, Tuple

from ai_rpg_world.application.common.exceptions import ApplicationException

from ai_rpg_world.application.world_graph.synchronized_action_registry import (
    SyncPrepareEntry,
    SynchronizedActionRegistry,
)
from ai_rpg_world.application.world_graph.world_flag_state import (
    MutableWorldFlagState,
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.enum.passage_change_cause import (
    PassageChangeCauseEnum,
)
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)
from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
    WorldGraphEffectService,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import (
    InteractionEffect,
)
from ai_rpg_world.domain.world_graph.value_object.synchronized_action_group import (
    SynchronizedActionGroup,
)


_logger = logging.getLogger(__name__)


_SUPPORTED_EFFECT_TYPES = frozenset({
    "SET_FLAG", "CLEAR_FLAG", "RESOLVE_ONGOING_CONDITION",
    "CHANGE_PASSAGE_STATE", "SHOW_MESSAGE",
})


_GroupOutcome = Literal["completed", "timed_out", "pending", "idle"]
_MessageCallback = Callable[
    [str, Literal["completed", "timed_out"], tuple[int, ...], str],
    None,
]


class SynchronizedActionResolverStageService:
    """毎 tick で sync group の完成 / タイムアウトを判定して効果を適用する。"""

    def __init__(
        self,
        *,
        groups: Iterable[SynchronizedActionGroup],
        registry: SynchronizedActionRegistry,
        spot_graph_repository: ISpotGraphRepository,
        spot_interior_repository: ISpotInteriorRepository,
        world_flag_state: MutableWorldFlagState,
        effect_service: WorldGraphEffectService | None = None,
        on_message: _MessageCallback | None = None,
    ) -> None:
        self._groups = tuple(groups)
        self._registry = registry
        self._spot_graph_repository = spot_graph_repository
        self._spot_interior_repository = spot_interior_repository
        self._world_flag_state = world_flag_state
        self._effect_service = effect_service or WorldGraphEffectService()
        self._on_message = on_message
        if on_message is None and any(
            effect.effect_type.value == "SHOW_MESSAGE"
            for group in self._groups
            for effect in (*group.on_complete, *group.on_timeout)
        ):
            raise ApplicationException(
                "synchronized_action_groups の SHOW_MESSAGE に観測配信が配線されていません"
            )

    def run(self, current_tick: WorldTick) -> None:
        if not self._groups:
            return
        graph = self._spot_graph_repository.find_graph()
        graph_dirty = False
        for group in self._groups:
            outcome = self._resolve_group(group, current_tick, graph)
            if outcome == "completed" or outcome == "timed_out":
                graph_dirty = True
        if graph_dirty:
            self._spot_graph_repository.save(graph)

    def _resolve_group(
        self,
        group: SynchronizedActionGroup,
        current_tick: WorldTick,
        graph: SpotGraphAggregate,
    ) -> _GroupOutcome:
        """1 group を解決する。"""
        # 各 required action の最古 prepare を取得
        per_action: dict[str, SyncPrepareEntry | None] = {
            aid: self._registry.find_oldest_for_action(aid)
            for aid in group.required_action_names
        }
        prepared_count = sum(1 for e in per_action.values() if e is not None)
        if prepared_count == 0:
            return "idle"

        # action 名が全部揃っていても、同じ一人が複数の役割を準備したなら
        # 完成させない。通常入口は二つ目を理由つきで拒否するが、snapshot 復元や
        # registry の直接利用が不正な組を作っても resolver 自身が不変条件を守る。
        prepared_player_ids = {
            entry.player_id for entry in per_action.values() if entry is not None
        }
        all_prepared = (
            prepared_count == len(group.required_action_names)
            and len(prepared_player_ids) == len(group.required_action_names)
        )
        # 窓判定: 最古 prepare から current_tick が window_ticks 以内か
        prepared_entries = [e for e in per_action.values() if e is not None]
        all_participants = [
            entry
            for action_name in group.required_action_names
            for entry in self._registry.entries_for(action_name)
        ]
        oldest_tick = min(e.prepare_tick for e in prepared_entries)
        within_window = (current_tick.value - oldest_tick) < group.window_ticks

        if all_prepared and within_window:
            self._apply_effects(
                group,
                "completed",
                group.on_complete,
                all_participants,
                graph,
            )
            self._clear_group_preps(group)
            return "completed"

        if not within_window:
            # 窓を超えてタイムアウト。on_timeout が空なら効果スキップ、
            # いずれにしても prepare はクリアする。
            if group.on_timeout:
                self._apply_effects(
                    group,
                    "timed_out",
                    group.on_timeout,
                    all_participants,
                    graph,
                )
            self._clear_group_preps(group)
            return "timed_out"

        # まだ窓内、かつ揃っていない
        return "pending"

    def _apply_effects(
        self,
        group: SynchronizedActionGroup,
        outcome: Literal["completed", "timed_out"],
        effects: Tuple[InteractionEffect, ...],
        participants: list[SyncPrepareEntry],
        graph: SpotGraphAggregate,
    ) -> None:
        """effect tuple を WorldGraphEffectService で適用し、結果を graph に反映する。"""
        # acting_object は無いので None。interior は使わない effect が前提
        # （CHANGE_PASSAGE_STATE / SET_FLAG / CLEAR_FLAG / SHOW_MESSAGE 等）。OBJECT 系は
        # 単純化のため未対応で、ここで warn する。
        from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior

        for eff in effects:
            if eff.effect_type.value not in _SUPPORTED_EFFECT_TYPES:
                _logger.warning(
                    "SynchronizedActionResolverStage: effect_type %s is not "
                    "supported (interior が無いため). 対応 effect: %s",
                    eff.effect_type.value,
                    sorted(_SUPPORTED_EFFECT_TYPES),
                )

        # 空の interior（このステージは特定スポットに紐付かないグローバル
        # 解決なので、effect は world-flag / passage / message 系を想定）。
        empty_interior = SpotInterior((), (), (), ())
        result = self._effect_service.apply_effects(
            interior=empty_interior,
            acting_object=None,
            effects=effects,
            world_flags=self._world_flag_state.as_frozen_set(),
        )
        recipients = tuple(sorted({entry.player_id for entry in participants}))
        if self._on_message is not None:
            for message in result.messages:
                self._on_message(group.group_id, outcome, recipients, message)
        # flags を反映
        self._world_flag_state.replace_from_interaction(
            result.new_flags,
            context=WorldFlagMutationContext(
                source=WorldFlagMutationSource.SYNCHRONIZED_ACTION,
                actor_player_id=None,
            ),
        )
        # passage 状態遷移を反映
        for spec in result.passage_state_updates:
            graph.set_connection_passage_state(
                ConnectionId.create(spec.connection_id),
                spec.new_state,
                traversable_override=spec.traversable_override,
                sound_permeability_override=spec.sound_permeability_override,
                cause=PassageChangeCauseEnum.SYNCHRONIZED_ACTION,
                # Issue #183: 複数 actor が prepare → resolve の連鎖を構成するため
                # 単一の起点 actor が選べない。多人数を 1 名に縮約すると誤解を
                # 招くので、現状は None (= 主体不明) として扱う。将来 actor 群
                # を保持できる構造を導入したら見直す。
                actor_entity_id=None,
            )

    def _clear_group_preps(self, group: SynchronizedActionGroup) -> None:
        """この group の required_action_names に紐付く全 prepare flag を削除。"""
        seen_flags: Set[str] = set()
        all_entries: List[SyncPrepareEntry] = []
        for aid in group.required_action_names:
            for e in self._registry.entries_for(aid):
                if e.flag in seen_flags:
                    continue
                seen_flags.add(e.flag)
                all_entries.append(e)
        self._registry.clear_entries(all_entries)
