"""現在のフェーズと、そこに入った経緯を表す値オブジェクト。

``phase`` 単独ではなく開始 tick と最終活動 tick を持つのは、会議の終了条件
3 つ (全員投票 / 沈黙上限 / tick 上限) のうち 2 つが経過時間で決まるため
(docs/memory_system/meeting_and_voting_design.md §3)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    GamePhaseTransitionException,
)


@dataclass(frozen=True)
class GamePhaseState:
    """フェーズ 1 区間ぶんの状態。

    Attributes:
        phase: いまどのモードか。
        started_at_tick: この区間に入った tick。会議の tick 上限の起点。
        last_activity_tick: 最後に発言等があった tick。沈黙上限の起点。
            区間に入った時点では ``started_at_tick`` と同じ値にする。0 の
            ままにすると、会議が始まった瞬間に沈黙上限を超えて即終了する。
        trigger: **この区間に入った理由**。会議なら招集のきっかけ
            (``emergency_button`` / ``body_report``)、自由時間へ戻る区間なら
            会議の終わり方 (``vote_concluded`` / ``silence`` / ``tick_limit``)。
            世界の初期状態だけ ``None`` になる (誰かが始めたわけではない)。
    """

    phase: GamePhase
    started_at_tick: int
    last_activity_tick: int
    trigger: Optional[str] = None

    def __post_init__(self) -> None:
        if self.started_at_tick < 0:
            raise GamePhaseTransitionException(
                f"started_at_tick は 0 以上である必要があります: {self.started_at_tick}"
            )
        if self.last_activity_tick < self.started_at_tick:
            # ここが崩れると沈黙の経過が負になり、会議が永久に終わらない。
            raise GamePhaseTransitionException(
                "last_activity_tick は started_at_tick 以上である必要があります: "
                f"start={self.started_at_tick} activity={self.last_activity_tick}"
            )

    def with_activity_at(self, tick: int) -> "GamePhaseState":
        """最終活動 tick を進めた新しい状態を返す。

        過去 tick では巻き戻さない。1 tick 内の並列処理で報告順が前後しうる
        ので、巻き戻すと沈黙判定が伸びて会議が終わらなくなる。
        """
        if tick <= self.last_activity_tick:
            return self
        return GamePhaseState(
            phase=self.phase,
            started_at_tick=self.started_at_tick,
            last_activity_tick=tick,
            trigger=self.trigger,
        )
