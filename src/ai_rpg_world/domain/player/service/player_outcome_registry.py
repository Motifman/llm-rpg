"""プレイヤー個別終局 outcome の追跡レジストリ (Phase E-3)。

`PlayerId → PlayerOutcomeEnum` の写像を保持し、handler / scenario_event /
game_end_evaluator から参照される。WorldFlagState と同じく runtime 寿命の
mutable state として扱う。

設計 §6 の集約原則:
- 各プレイヤーは UNRESOLVED で始まる
- 終局遷移は 1 回限り (UNRESOLVED → RESCUED/DEAD/STRANDED)
- 一度確定した outcome は上書きしない (`set_outcome` は冪等的)
- 全プレイヤーが確定したら `all_resolved` で true

set 時に optional callback を呼べるので、observation 経路で「○○が
死亡した」を通知する用途に使える。
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


# (player_id, old_outcome, new_outcome) を受ける callback。
# observation event 発火等に使う想定。
OutcomeChangedCallback = Callable[[PlayerId, PlayerOutcomeEnum, PlayerOutcomeEnum], None]


class PlayerOutcomeRegistry:
    """プレイヤー個別 outcome の mutable 写像。

    new_for_players(player_ids) で全員 UNRESOLVED で初期化、
    set_outcome(player_id, outcome) で 1 度だけ遷移、
    all_resolved() / unresolved_player_ids() で集約状況を問い合わせる。
    """

    def __init__(self) -> None:
        self._outcomes: Dict[int, PlayerOutcomeEnum] = {}
        self._callbacks: List[OutcomeChangedCallback] = []

    @classmethod
    def new_for_players(cls, player_ids: List[PlayerId]) -> "PlayerOutcomeRegistry":
        """指定プレイヤー全員を UNRESOLVED で初期化したレジストリを返す。"""
        reg = cls()
        for pid in player_ids:
            reg._outcomes[int(pid)] = PlayerOutcomeEnum.UNRESOLVED
        return reg

    def register_callback(self, callback: OutcomeChangedCallback) -> None:
        """outcome 変化時に呼ばれる callback を登録する。複数登録可。"""
        self._callbacks.append(callback)

    def get_outcome(self, player_id: PlayerId) -> PlayerOutcomeEnum:
        """登録されていないプレイヤーは UNRESOLVED を返す (auto-init)。"""
        return self._outcomes.get(int(player_id), PlayerOutcomeEnum.UNRESOLVED)

    def set_outcome(self, player_id: PlayerId, outcome: PlayerOutcomeEnum) -> bool:
        """outcome を 1 度だけ確定させる。

        Returns:
            True if outcome was changed (initial transition から resolved へ);
            False if already resolved (no-op、既存値を保持)。
        """
        pid_key = int(player_id)
        current = self._outcomes.get(pid_key, PlayerOutcomeEnum.UNRESOLVED)
        # 既に resolved なら冪等で no-op (上書きしない)
        if current.is_resolved:
            return False
        # UNRESOLVED → UNRESOLVED の遷移は無意味なので skip
        if outcome is PlayerOutcomeEnum.UNRESOLVED:
            return False
        self._outcomes[pid_key] = outcome
        # silent failure fix: 1 件の callback 失敗が後続 callback (例: 観測 emit
        # と trace 記録の両方を bind しているケース) を巻き添えにしないよう、
        # 各 callback の例外は log に残してから他 callback を継続する。
        # 既に _outcomes は更新済みなので、後続 callback は新 outcome を見れる。
        import logging
        _logger = logging.getLogger(__name__)
        for callback in self._callbacks:
            try:
                callback(player_id, current, outcome)
            except Exception:
                _logger.exception(
                    "outcome callback failed for player_id=%s (%s → %s)",
                    int(player_id), current.value, outcome.value,
                )
        return True

    def all_resolved(self) -> bool:
        """全プレイヤーの outcome が確定 (UNRESOLVED 以外) しているか。

        空 registry は True を返す (vacuous: 「全員」が空なら全員確定済み)。
        """
        return all(o.is_resolved for o in self._outcomes.values())

    def unresolved_player_ids(self) -> List[PlayerId]:
        """まだ UNRESOLVED のプレイヤー ID のリスト。"""
        return [
            PlayerId(pid)
            for pid, o in self._outcomes.items()
            if o is PlayerOutcomeEnum.UNRESOLVED
        ]

    def snapshot(self) -> Dict[int, PlayerOutcomeEnum]:
        """全プレイヤーの現在 outcome を不変な dict として返す (デバッグ・ログ用)。"""
        return dict(self._outcomes)
