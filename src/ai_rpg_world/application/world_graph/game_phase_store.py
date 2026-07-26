"""世界のフェーズ (自由時間 / 会議) を保持する per-world store。

**per-Being ではなく per-world。** フェーズは世界全体のモードで、プレイヤー
ごとに違うことは無い。したがって `BeingMemorySnapshotService` ではなく
world snapshot 側 (`GamePhaseSubsystemCodec`) に載せる。

排他は遷移メソッドの形で保証する。``current`` は常にちょうど 1 つで、
「会議でも自由時間でもある」状態を作る手段が無い
(docs/memory_system/meeting_and_voting_design.md §2.1)。

``MutableWorldFlagState`` と並ぶ、application 層に置く world 単位の可変
状態である。
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    GamePhaseTransitionException,
)
from ai_rpg_world.domain.world_graph.value_object.game_phase_state import (
    GamePhaseState,
)


class GamePhaseStore:
    """現在のフェーズと、直近の遷移履歴を持つ。"""

    #: 保持する遷移履歴の上限 (初期状態を含む)。長走 run で無限に伸びると
    #: snapshot が膨らみ続ける。分析に要るのは直近の遷移なので古い方から捨てる。
    MAX_HISTORY = 64

    def __init__(self, *, initial_tick: int = 0) -> None:
        initial = GamePhaseState(
            phase=GamePhase.FREE_ROAM,
            started_at_tick=initial_tick,
            last_activity_tick=initial_tick,
            trigger=None,
        )
        self._current: GamePhaseState = initial
        self._history: List[GamePhaseState] = [initial]

    @property
    def current(self) -> GamePhaseState:
        """いまのフェーズ。常にちょうど 1 つ。"""
        return self._current

    @property
    def history(self) -> Tuple[GamePhaseState, ...]:
        """遷移した順の履歴 (初期状態を含む)。"""
        return tuple(self._history)

    def is_meeting(self) -> bool:
        """会議中か。toolset の選択と tool の fail-fast が参照する。"""
        return self._current.phase is GamePhase.MEETING

    def begin_meeting(self, *, tick: int, trigger: str) -> GamePhaseState:
        """会議を始める。既に会議中なら例外。

        黙って 2 回目を通すと開始 tick が上書きされ、会議の tick 上限が
        伸び続ける。1 tick 内で 2 人が緊急ボタンを押すのは実際に起こりうる
        ので、2 人目には「もう始まっている」を返す必要がある。
        """
        if self._current.phase is GamePhase.MEETING:
            raise GamePhaseTransitionException(
                "会議はすでに始まっています "
                f"(started_at_tick={self._current.started_at_tick})"
            )
        return self._transition_to(
            GamePhase.MEETING, tick=tick, trigger=trigger
        )

    def end_meeting(self, *, tick: int, reason: str) -> GamePhaseState:
        """会議を終えて自由時間へ戻る。会議中でなければ例外。

        ``reason`` は次の区間の ``trigger`` として残す (``vote_concluded`` /
        ``silence`` / ``tick_limit``)。会議が機能しているかの指標になる。
        """
        if self._current.phase is not GamePhase.MEETING:
            raise GamePhaseTransitionException(
                "会議中ではないので終了できません "
                f"(current={self._current.phase.value})"
            )
        return self._transition_to(
            GamePhase.FREE_ROAM, tick=tick, trigger=reason
        )

    def note_activity(self, *, tick: int) -> None:
        """発言等があったことを記録する (沈黙上限の起点を進める)。

        履歴は伸ばさない。記録するのは遷移だけで、活動は現在区間の更新に
        とどめる。
        """
        self._current = self._current.with_activity_at(tick)
        self._history[-1] = self._current

    def ticks_since_activity(self, *, tick: int) -> int:
        """最終活動からの経過 tick。沈黙上限の判定に使う。"""
        return max(0, tick - self._current.last_activity_tick)

    def replace_all(
        self, *, current: GamePhaseState, history: Sequence[GamePhaseState]
    ) -> None:
        """snapshot 復元用に中身を丸ごと置き換える。

        追記ではなく置換にするのは、再開のたびに履歴が積み増されるのを
        避けるため。
        """
        self._current = current
        self._history = list(history)[-self.MAX_HISTORY :]
        if not self._history:
            self._history = [current]

    def _transition_to(
        self, phase: GamePhase, *, tick: int, trigger: str
    ) -> GamePhaseState:
        state = GamePhaseState(
            phase=phase,
            started_at_tick=tick,
            last_activity_tick=tick,
            trigger=trigger,
        )
        self._current = state
        self._history.append(state)
        if len(self._history) > self.MAX_HISTORY:
            del self._history[: len(self._history) - self.MAX_HISTORY]
        return state
