"""tick経過で欲求を自然増加させるステージサービス。

SpotGraphSimulationApplicationService の tick パイプラインに組み込み、
毎tick で全プレイヤーの空腹・疲労を緩やかに増加させる。

Phase v2-hunger: HUNGER が max (= 限界) に達したプレイヤーには、毎 tick
HP を漸減させる Minecraft 風の飢餓ダメージも適用する。HP 0 になった場合
は PlayerStatusAggregate が PlayerDownedEvent を積み、event_publisher 経由
で PlayerDownedOutcomeHandler が DEAD outcome を確定させる (E-3a 経路)。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_logger = logging.getLogger(__name__)


# デフォルトの増加レート（tick あたり）
DEFAULT_NEED_RATES: Dict[NeedType, int] = {
    NeedType.HUNGER: 1,   # 100tick で空腹が限界に達する
    NeedType.FATIGUE: 0,  # 疲労は行動 (interact/travel/attack) でのみ増える
                          # — 「何もしなくても 100tick で詰む」構造を解消する
                          # ため自然増加を切る (Y_after_pr634 後続)。
                          # シナリオ側で必要なら rates 引数で上書きできる。
}


class SpotGraphNeedsDecayStageService:
    """毎tick で全プレイヤーの欲求を自然増加させる。

    ``_SpotGraphTickStage`` Protocol に準拠。
    ``SpotGraphSimulationApplicationService`` の tick パイプラインに
    ``needs_decay_stage`` として注入する。

    Args:
        player_status_repository: PlayerStatusAggregate を引く repo。
        rates: 各 NeedType の増加 rate (tick あたり)。default は HUNGER + FATIGUE
            ともに +1/tick。0 にすると該当 need は増加しない。
        starvation_damage_per_tick: HUNGER が limit に達したプレイヤーに
            毎 tick 適用する HP ダメージ。default 0 (= 無効、後方互換)。
            v2 survival_island のような飢餓メカニクスが要るシナリオは
            正の値 (例: 1) を指定する。0 にしておけば既存シナリオ
            (脱出ゲーム等) の挙動は完全に不変。
        event_publisher: HP 0 で発生する PlayerDownedEvent を流すための
            publisher。None なら events は aggregate に残り続け (将来
            別経路で flush されることを想定)、PlayerDownedOutcomeHandler
            の自動連鎖は起きない。
        state_collapse_evidence_transcriber: PR-D。hunger max 到達を高
            salience の ``BeliefEvidence`` に転記する transcriber
            (``StateCollapseEvidenceTranscriber``)。None なら完全 no-op
            (= STATE_COLLAPSE_EVIDENCE_ENABLED OFF 相当、導入前と挙動不変)。
        state_collapse_being_id_resolver: player_id から being_id を解決する
            callable。transcriber と対で必要 (どちらか None なら no-op)。
    """

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        *,
        rates: Dict[NeedType, int] | None = None,
        starvation_damage_per_tick: int = 0,
        fatigue_critical_damage_per_tick: int = 0,
        fatigue_critical_threshold: int = 95,
        event_publisher: Optional[Any] = None,
        state_collapse_evidence_transcriber: Optional[Any] = None,
        state_collapse_being_id_resolver: Optional[
            Callable[[PlayerId], Optional[Any]]
        ] = None,
    ) -> None:
        self._player_status_repository = player_status_repository
        self._rates = rates or dict(DEFAULT_NEED_RATES)
        self._starvation_damage_per_tick = max(0, starvation_damage_per_tick)
        # PR β: 疲労が threshold (default 95) を超えたプレイヤーに毎 tick
        # 微小 HP ダメージを与える。「限界まで疲弊すると徐々に体が壊れる」を
        # 表現するための飢餓と同型のメカニクス。default 0 (= 無効、後方互換)。
        self._fatigue_critical_damage_per_tick = max(0, fatigue_critical_damage_per_tick)
        self._fatigue_critical_threshold = fatigue_critical_threshold
        self._event_publisher = event_publisher
        self._state_collapse_evidence_transcriber = state_collapse_evidence_transcriber
        self._state_collapse_being_id_resolver = state_collapse_being_id_resolver

    def set_event_publisher(self, publisher: Optional[Any]) -> None:
        """publisher を後付け注入する (runtime 順序依存の解消用)。

        weather / food_spoilage と同じ pattern。constructor は publisher 無しで
        作っておき、runtime 構築完了後に bind する。
        """
        self._event_publisher = publisher

    def set_state_collapse_evidence_wiring(
        self,
        transcriber: Optional[Any],
        being_id_resolver: Optional[Callable[[PlayerId], Optional[Any]]],
    ) -> None:
        """PR-D: transcriber / being_id_resolver を後付け注入する。

        ``set_event_publisher`` と同じ pattern (runtime 構築完了後に bind)。
        """
        self._state_collapse_evidence_transcriber = transcriber
        self._state_collapse_being_id_resolver = being_id_resolver

    def run(self, current_tick: WorldTick) -> None:
        """全プレイヤーの欲求を増加させ、一括保存する + 飢餓ダメージを適用。"""
        updated = []
        starvation_events: list = []
        for status in self._player_status_repository.find_all():
            # ダウン中は欲求の自然増加を停止（蘇生後に蓄積しない設計）
            if not status.can_act():
                continue
            if len(status.needs) == 0:
                continue
            changed = False
            for need_type, rate in self._rates.items():
                if rate <= 0:
                    continue
                need = status.needs.get(need_type)
                if need is not None and need.value < need.max_value:
                    status.increase_need(need_type, rate)
                    changed = True
            # 飢餓ダメージ: HUNGER が max に達しているプレイヤーに毎 tick 適用。
            # increase_need 後の値で判定するので「今 tick で max になった」
            # ケースも即時に damage が走る (体感的に違和感は無い)。
            if self._starvation_damage_per_tick > 0:
                hunger = status.needs.get(NeedType.HUNGER)
                if hunger is not None and hunger.value >= hunger.max_value:
                    status.apply_damage(self._starvation_damage_per_tick)
                    changed = True
                    # apply_damage が HP 0 → PlayerDownedEvent を積む。
                    # publisher が居れば回収して後で流す (空 list は no-op)。
                    if self._event_publisher is not None:
                        starvation_events.extend(status.get_events())
                        status.clear_events()
            # PR-D: hunger max 到達を高 salience evidence に転記する。
            # starvation_damage_per_tick の設定 (飢餓ダメージの有無) とは独立
            # (「空腹が限界に達した」という事実そのものが対象)。
            self._sync_hunger_max_evidence(status)
            # PR β: 疲労限界 (>= threshold, default 95) でも HP 微減。
            # starvation と同じ event 回収パターンに乗せる。
            if self._fatigue_critical_damage_per_tick > 0:
                fatigue = status.needs.get(NeedType.FATIGUE)
                if (
                    fatigue is not None
                    and fatigue.value >= self._fatigue_critical_threshold
                ):
                    status.apply_damage(self._fatigue_critical_damage_per_tick)
                    changed = True
                    if self._event_publisher is not None:
                        starvation_events.extend(status.get_events())
                        status.clear_events()
            if changed:
                updated.append(status)
        if updated:
            self._player_status_repository.save_all(updated)
        # 全プレイヤーの save が完了してから event を flush する (順序: 状態
        # 変更 → 永続化 → event 配信)
        if starvation_events and self._event_publisher is not None:
            self._event_publisher.publish_all(starvation_events)

    def _sync_hunger_max_evidence(self, status: Any) -> None:
        """PR-D: hunger.value と max_value を比較し、transcriber の dedup 状態を
        同期する。

        - max 到達中 (>=): ``record_hunger_max_evidence`` (transcriber 側で
          既に記録済みなら二重には積まれない)
        - max 未満: ``clear_hunger_max_state`` (食事等で回復した場合に次回
          再到達したとき新しい evidence を積めるようにする)

        transcriber / being_id_resolver のどちらかが未配線、または
        being_id が解決できないときは完全に no-op。evidence 記録は
        best-effort な副作用なので、transcriber 側の例外はここで握って
        tick 処理全体を止めない。
        """
        transcriber = self._state_collapse_evidence_transcriber
        resolver = self._state_collapse_being_id_resolver
        if transcriber is None or resolver is None:
            return
        hunger = status.needs.get(NeedType.HUNGER)
        if hunger is None:
            return
        try:
            being_id = resolver(status.player_id)
        except Exception:
            _logger.exception(
                "state_collapse_being_id_resolver failed for player_id=%s",
                status.player_id,
            )
            return
        if being_id is None:
            return
        try:
            if hunger.value >= hunger.max_value:
                transcriber.record_hunger_max_evidence(being_id)
            else:
                transcriber.clear_hunger_max_state(being_id)
        except Exception:
            _logger.exception(
                "state_collapse_evidence_transcriber failed for being_id=%s",
                being_id,
            )
